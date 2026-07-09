import json
import multiprocessing
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from faster_whisper import WhisperModel

import config
from logger import get_logger

logger = get_logger(__name__)

# 线程本地存储：每个线程持有自己的 WhisperModel，避免跨线程共享非线程安全模型
_thread_local = threading.local()


def _get_thread_whisper_model(model_name, device, compute_type):
    """获取当前线程的 WhisperModel 实例，首次调用时加载（同一线程复用）"""
    key = f"{model_name}|{device}|{compute_type}"
    if getattr(_thread_local, "model_key", None) != key:
        _thread_local.model = WhisperModel(model_name, device=device, compute_type=compute_type)
        _thread_local.model_key = key
    return _thread_local.model


def _find_exe(name: str) -> str:
    """Resolve ffmpeg/ffprobe binaries across common Windows install paths."""
    found = shutil.which(name)
    if found:
        return found
    candidates = [
        r"D:\ffmpeg\bin",
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"C:\ProgramData\chocolatey\bin",
    ]
    for directory in candidates:
        path = os.path.join(directory, name + ".exe")
        if os.path.isfile(path):
            return path
    return name


_FFMPEG = _find_exe("ffmpeg")
_FFPROBE = _find_exe("ffprobe")
logger.info("ffmpeg: %s  ffprobe: %s", _FFMPEG, _FFPROBE)

_PARALLEL_MIN_SEC = 90
_MAX_CHUNK_SEC = 60
_MIN_SILENCE_MS = 500
_SILENCE_THRESH_DB = -40
_MAX_WORKERS = 4

_BASE_INITIAL_PROMPT = "以下是普通话会议录音，请使用简体中文输出。"
_INITIAL_PROMPT_MAX_TOKENS = 200

_HALLUCINATION_PHRASES = [
    "请使用简体中文输出",
    "以下是普通话会议录音",
    "本次会议涉及以下专有名词",
    "本次会议涉及以下专有术语",
    "字幕由",
    "感谢收看",
    "请订阅",
]


def _estimate_tokens(text: str) -> int:
    """Rough token estimate used to cap Whisper initial_prompt length."""
    chinese = sum(1 for c in text if "一" <= c <= "鿿")
    other = len(text) - chinese
    return int(chinese * 2.0 + other * 0.5)


def _build_initial_prompt(terms: list[str] | None) -> str:
    """Build a bounded initial prompt with optional terminology injection."""
    normalized = [term.strip() for term in (terms or []) if term and term.strip()]
    if not normalized:
        return _BASE_INITIAL_PROMPT

    kept: list[str] = []
    for term in normalized:
        candidate_terms = kept + [term]
        candidate = (
            f"{_BASE_INITIAL_PROMPT}"
            f"本次会议涉及以下专有术语，请优先识别：{'，'.join(candidate_terms)}。"
        )
        if _estimate_tokens(candidate) > _INITIAL_PROMPT_MAX_TOKENS:
            break
        kept.append(term)

    if not kept:
        return _BASE_INITIAL_PROMPT
    return f"{_BASE_INITIAL_PROMPT}本次会议涉及以下专有术语，请优先识别：{'，'.join(kept)}。"


def _is_segment_hallucination(text: str) -> bool:
    """Return True if a segment matches a known Whisper hallucination pattern."""
    stripped = text.strip()
    if not stripped:
        return True
    for phrase in _HALLUCINATION_PHRASES:
        if phrase in stripped:
            return True
    clean = re.sub(r"[\s,，。！？、；：\"'‘’“”「」【】]", "", stripped)
    if len(clean) >= 5:
        for unit_len in range(1, 5):
            if re.search(r"(.{" + str(unit_len) + r"})\1{4,}", clean):
                return True
    return False


def _detect_silence_ffmpeg(audio_path: str, min_silence_ms: int, thresh_db: int) -> list:
    """Return list of (start_s, end_s) silence intervals via ffmpeg silencedetect."""
    try:
        result = subprocess.run(
            [
                _FFMPEG,
                "-i",
                audio_path,
                "-af",
                f"silencedetect=noise={thresh_db}dB:d={min_silence_ms / 1000:.3f}",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        starts, silences = [], []
        for line in result.stderr.splitlines():
            m_start = re.search(r"silence_start:\s*([\d.]+)", line)
            m_end = re.search(r"silence_end:\s*([\d.]+)", line)
            if m_start:
                starts.append(float(m_start.group(1)))
            if m_end and starts:
                silences.append((starts.pop(0), float(m_end.group(1))))
        return silences
    except Exception as exc:
        logger.warning("silencedetect 失败: %s", exc)
        return []


def _split_audio_ffmpeg(audio_path: str, duration_s: float) -> tuple:
    """Split audio at silence boundaries into temp WAV chunks."""
    silences = _detect_silence_ffmpeg(audio_path, _MIN_SILENCE_MS, _SILENCE_THRESH_DB)

    cut_points = [0.0]
    for start_s, end_s in silences:
        cut_points.append((start_s + end_s) / 2.0)
    cut_points.append(duration_s)

    bounds: list[tuple[float, float]] = []
    chunk_start = 0.0
    for index in range(1, len(cut_points)):
        if cut_points[index] - chunk_start >= _MAX_CHUNK_SEC or index == len(cut_points) - 1:
            bounds.append((chunk_start, cut_points[index]))
            chunk_start = cut_points[index]

    if not bounds:
        bounds = [(0.0, duration_s)]

    tmpdir = tempfile.mkdtemp(prefix="asr_chunks_")
    chunks = []
    for idx, (start_s, end_s) in enumerate(bounds):
        out_path = os.path.join(tmpdir, f"chunk_{idx:03d}.wav")
        subprocess.run(
            [
                _FFMPEG,
                "-y",
                "-i",
                audio_path,
                "-ss",
                f"{start_s:.3f}",
                "-to",
                f"{end_s:.3f}",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-acodec",
                "pcm_s16le",
                out_path,
            ],
            capture_output=True,
            check=True,
            timeout=60,
        )
        chunks.append({"index": idx, "path": out_path, "start_s": start_s, "end_s": end_s})

    logger.info(
        "音频切分为 %d 块，最长 %.1fs",
        len(chunks),
        max(chunk["end_s"] - chunk["start_s"] for chunk in chunks),
    )
    return chunks, tmpdir


def _transcribe_chunk_worker(args: tuple) -> dict:
    """Worker executed in a thread for long-audio parallel transcription.

    Uses thread-local WhisperModel so each thread loads the model only once.
    Threads share the same process address space, so OS-level mmap deduplication
    keeps physical memory for read-only model weights at ~1x (vs N×processes).
    """
    chunk_index, chunk_path, start_offset_s, model_name, device, compute_type, language, prompt = args
    try:
        model = _get_thread_whisper_model(model_name, device, compute_type)
        segments_gen, _ = model.transcribe(
            chunk_path,
            language=language,
            beam_size=5,
            initial_prompt=prompt,
        )
        segments = []
        for seg in segments_gen:
            segments.append(
                {
                    "id": seg.id,
                    "text": seg.text.strip(),
                    "start": seg.start + start_offset_s,
                    "end": seg.end + start_offset_s,
                    "duration": seg.end - seg.start,
                    "timestamp": time.time(),
                }
            )
        return {"index": chunk_index, "segments": segments, "success": True}
    except Exception as exc:
        return {"index": chunk_index, "segments": [], "success": False, "error": str(exc)}


def _get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds via a single fast ffprobe call."""
    try:
        result = subprocess.run(
            [_FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        info = json.loads(result.stdout)
        return float(info.get("format", {}).get("duration", 0))
    except Exception as exc:
        logger.warning("_get_audio_duration 失败: %s", exc)
        return 0.0


def _get_audio_info(audio_path):
    """通过 ffprobe 获取音频时长和音量信息，无需 pydub。"""
    try:
        result = subprocess.run(
            [
                _FFPROBE,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                audio_path,
            ],
            capture_output=True,
            text=False,
            timeout=30,
        )
        info = json.loads(result.stdout.decode("utf-8", errors="replace"))

        duration_sec = float(info.get("format", {}).get("duration", 0))
        streams = info.get("streams", [])
        audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)

        if audio_stream:
            try:
                loud_result = subprocess.run(
                    [
                        _FFPROBE,
                        "-v",
                        "quiet",
                        "-print_format",
                        "json",
                        "-show_entries",
                        "frame_tags=lavfi.r128.I",
                        "-f",
                        "lavfi",
                        # lavfi amovie= 使用单引号包裹路径，支持含空格的文件名
                        "amovie='{path}',ebur128=metadata=1".format(
                            path=audio_path.replace("'", "\\'")
                        ),
                    ],
                    capture_output=True,
                    text=False,
                    timeout=30,
                )
                loud_info = json.loads(loud_result.stdout.decode("utf-8", errors="replace"))
                frames = loud_info.get("frames", [])
                if frames:
                    i_values = [
                        float(frame.get("tags", {}).get("lavfi.r128.I", "-70"))
                        for frame in frames
                    ]
                    integrated_loudness = sum(i_values) / len(i_values) if i_values else -30
                    noise_level = min(1.0, max(0.0, (integrated_loudness + 30) / 25))
                    return duration_sec, noise_level
            except Exception:
                pass

        return duration_sec, 0.3
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as exc:
        logger.warning("ffprobe 获取音频信息失败: %s", exc)
        return 0, 0.3


class ASREngine:
    """语音识别引擎，基于 Faster-Whisper (CTranslate2)。"""

    def __init__(self, model_name=None, device=None, compute_type=None):
        logger.info("正在初始化语音识别模型...")
        try:
            self.model = WhisperModel(
                model_name or config.WHISPER_MODEL,
                device=device or config.WHISPER_DEVICE,
                compute_type=compute_type or config.WHISPER_COMPUTE_TYPE,
            )
            logger.info("Faster-Whisper 模型加载完成")
        except Exception as exc:
            logger.error("加载失败 %s，回退到 tiny 模型 + int8 量化", exc)
            self.model = WhisperModel("tiny", device="cpu", compute_type="int8")

    def _get_beam_size(self, duration_sec):
        return 3 if duration_sec < 300 else (8 if duration_sec > 1800 else 5)

    def _build_segment(self, idx, seg):
        return {
            "id": idx,
            "text": seg.text.strip(),
            "start": float(seg.start),
            "end": float(seg.end),
            "duration": float(seg.end - seg.start),
            "timestamp": time.time(),
        }

    def transcribe_iter(self, audio_path, progress_callback=None, terms=None):
        duration_sec = _get_audio_duration(audio_path)
        beam_size = self._get_beam_size(duration_sec)
        prompt = _build_initial_prompt(terms)

        segments_raw, info = self.model.transcribe(
            audio_path,
            language=config.WHISPER_LANGUAGE,
            beam_size=beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=prompt,
        )

        total_est = int(info.duration / 5) + 1
        for idx, seg in enumerate(segments_raw):
            item = self._build_segment(idx, seg)
            if _is_segment_hallucination(item["text"]):
                continue
            if progress_callback:
                progress_callback(idx + 1, total_est)
            yield item, info.duration

    def transcribe(self, audio_path, progress_callback=None, terms=None):
        segments = []
        duration = 0.0
        for item, dur in self.transcribe_iter(audio_path, progress_callback, terms=terms):
            segments.append(item)
            duration = dur
        return segments, duration

    def transcribe_parallel_iter(self, audio_path, terms=None):
        """Parallel chunked transcription for long audio."""
        duration_s = _get_audio_duration(audio_path)
        chunks, tmpdir = _split_audio_ffmpeg(audio_path, duration_s or _PARALLEL_MIN_SEC)
        chunk_count = len(chunks)
        worker_count = min(multiprocessing.cpu_count(), chunk_count, _MAX_WORKERS)
        logger.info("并行转写：%d 块，%d 进程", chunk_count, worker_count)

        prompt = _build_initial_prompt(terms)
        tasks = [
            (
                chunk["index"],
                chunk["path"],
                chunk["start_s"],
                config.WHISPER_MODEL,
                config.WHISPER_DEVICE,
                config.WHISPER_COMPUTE_TYPE,
                config.WHISPER_LANGUAGE,
                prompt,
            )
            for chunk in chunks
        ]

        results: dict[int, dict] = {}
        try:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {executor.submit(_transcribe_chunk_worker, task): task[0] for task in tasks}
                for future in as_completed(futures):
                    result = future.result()
                    results[result["index"]] = result
                    completed = len(results)
                    if not result["success"]:
                        logger.warning("块 %d 转写失败: %s", result["index"], result.get("error"))
                    yield {
                        "type": "chunk_done",
                        "completed": completed,
                        "total": chunk_count,
                        "pct": int(completed / chunk_count * 55),
                    }
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        all_segments = []
        for idx in sorted(results.keys()):
            result = results[idx]
            if result["success"]:
                all_segments.extend(result["segments"])
        all_segments = [seg for seg in all_segments if not _is_segment_hallucination(seg["text"])]
        all_segments.sort(key=lambda seg: seg["start"])
        yield {"type": "complete", "segments": all_segments}

    @staticmethod
    def classify_duration(duration):
        if duration < 300:
            return "short"
        if duration < 1800:
            return "medium"
        return "long"

    @staticmethod
    def classify_meeting_type(duration, num_speakers, noise_level):
        return ASREngine.classify_duration(duration), "unknown"


_asr_engine_instance: ASREngine | None = None


def get_asr_engine() -> ASREngine:
    """返回 ASREngine 单例，避免重复加载 WhisperModel。"""
    global _asr_engine_instance
    if _asr_engine_instance is None:
        _asr_engine_instance = ASREngine()
    return _asr_engine_instance
