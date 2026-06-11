import json
import multiprocessing
import os
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from faster_whisper import WhisperModel

import config
from logger import get_logger

logger = get_logger(__name__)

# ── Parallel chunking constants ──────────────────────────────────────────────
_PARALLEL_MIN_SEC  = 90    # use parallel only when audio exceeds this duration
_MAX_CHUNK_SEC     = 60    # each chunk is at most this long
_MIN_SILENCE_MS    = 500   # detect silence gaps of at least this length
_SILENCE_THRESH_DB = -40   # dBFS threshold for silence detection
_MAX_WORKERS       = 4     # cap parallelism regardless of CPU count


def _detect_silence_ffmpeg(audio_path: str, min_silence_ms: int, thresh_db: int) -> list:
    """Return list of (start_s, end_s) silence intervals via ffmpeg silencedetect."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", audio_path,
                "-af", f"silencedetect=noise={thresh_db}dB:d={min_silence_ms / 1000:.3f}",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=120,
        )
        starts, silences = [], []
        for line in result.stderr.splitlines():
            m_start = re.search(r"silence_start:\s*([\d.]+)", line)
            m_end   = re.search(r"silence_end:\s*([\d.]+)", line)
            if m_start:
                starts.append(float(m_start.group(1)))
            if m_end and starts:
                silences.append((starts.pop(0), float(m_end.group(1))))
        return silences
    except Exception as e:
        logger.warning("silencedetect 失败: %s", e)
        return []


def _split_audio_ffmpeg(audio_path: str, duration_s: float) -> tuple:
    """Split audio at silence boundaries into temp WAV chunks.

    Returns (chunk_list, tmpdir) where chunk_list is
    [{"index": int, "path": str, "start_s": float, "end_s": float}, ...].
    Caller must delete tmpdir when done.
    """
    silences = _detect_silence_ffmpeg(audio_path, _MIN_SILENCE_MS, _SILENCE_THRESH_DB)

    # Build candidate cut points from silence midpoints
    cut_points = [0.0]
    for s_start, s_end in silences:
        cut_points.append((s_start + s_end) / 2.0)
    cut_points.append(duration_s)

    # Merge into chunks that stay under _MAX_CHUNK_SEC
    bounds: list[tuple[float, float]] = []
    chunk_start = 0.0
    for i in range(1, len(cut_points)):
        if cut_points[i] - chunk_start >= _MAX_CHUNK_SEC or i == len(cut_points) - 1:
            bounds.append((chunk_start, cut_points[i]))
            chunk_start = cut_points[i]

    if not bounds:
        bounds = [(0.0, duration_s)]

    tmpdir = tempfile.mkdtemp(prefix="asr_chunks_")
    chunks = []
    for idx, (start, end) in enumerate(bounds):
        out_path = os.path.join(tmpdir, f"chunk_{idx:03d}.wav")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", audio_path,
                "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
                out_path,
            ],
            capture_output=True, check=True, timeout=60,
        )
        chunks.append({"index": idx, "path": out_path, "start_s": start, "end_s": end})

    logger.info("音频切分为 %d 块，最长 %.1fs", len(chunks),
                max(c["end_s"] - c["start_s"] for c in chunks))
    return chunks, tmpdir


def _transcribe_chunk_worker(args: tuple) -> dict:
    """Top-level worker executed in a subprocess — must stay at module level for pickling."""
    chunk_index, chunk_path, start_offset_s, model_name, device, compute_type, language, prompt = args
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        segments_gen, _ = model.transcribe(
            chunk_path,
            language=language,
            beam_size=5,
            initial_prompt=prompt,
        )
        segments = []
        for seg in segments_gen:
            segments.append({
                "id":        seg.id,
                "text":      seg.text.strip(),
                "start":     seg.start + start_offset_s,
                "end":       seg.end   + start_offset_s,
                "duration":  seg.end - seg.start,
                "timestamp": time.time(),
            })
        return {"index": chunk_index, "segments": segments, "success": True}
    except Exception as exc:
        return {"index": chunk_index, "segments": [], "success": False, "error": str(exc)}


def _get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds via a single fast ffprobe call (no loudness analysis)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
            capture_output=True, text=True, timeout=10,
        )
        info = json.loads(result.stdout)
        return float(info.get("format", {}).get("duration", 0))
    except Exception as e:
        logger.warning("_get_audio_duration 失败: %s", e)
        return 0.0


def _get_audio_info(audio_path):
    """通过 ffprobe 获取音频时长和音量信息，无需 pydub"""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                audio_path,
            ],
            capture_output=True,
            text=False,       # 二进制模式，避免 GBK 解码错误
            timeout=30,
        )
        info = json.loads(result.stdout.decode("utf-8", errors="replace"))

        duration_sec = float(info.get("format", {}).get("duration", 0))

        # 从 stream 中获取音量相关信息
        streams = info.get("streams", [])
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        # 用 RMS / max_volume 等指标估算噪声水平
        if audio_stream:
            # 尝试获取 EBU R128 响度信息
            try:
                loud_result = subprocess.run(
                    [
                        "ffprobe",
                        "-v", "quiet",
                        "-print_format", "json",
                        "-show_entries",
                        "frame_tags=lavfi.r128.I",
                        "-f", "lavfi",
                        f"amovie={audio_path},ebur128=metadata=1",
                    ],
                    capture_output=True,
                    text=False,       # 二进制模式，避免 GBK 解码错误
                    timeout=30,
                )
                loud_info = json.loads(loud_result.stdout.decode("utf-8", errors="replace"))
                frames = loud_info.get("frames", [])
                if frames:
                    i_values = [
                        float(f.get("tags", {}).get("lavfi.r128.I", "-70"))
                        for f in frames
                    ]
                    integrated_loudness = sum(i_values) / len(i_values) if i_values else -30
                    # 映射到 [0, 1]，-30 LUFS 视为安静, -5 LUFS 视为极吵
                    noise_level = min(1.0, max(0.0, (integrated_loudness + 30) / 25))
                    return duration_sec, noise_level
            except Exception:
                pass

        # 回退：无法获取响度时使用默认值
        noise_level = 0.3
        return duration_sec, noise_level

    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        logger.warning("ffprobe 获取音频信息失败: %s", e)
        return 0, 0.3


# initial_prompt 最大 token 数（超出则截断）
_INITIAL_PROMPT_MAX_TOKENS = 200


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数：中文约 2 token/字，英文/数字约 0.5 token/字符"""
    chinese = sum(1 for c in text if '一' <= c <= '鿿')
    other = len(text) - chinese
    return int(chinese * 2.0 + other * 0.5)


def _build_initial_prompt(terms: list[str]) -> str:
    """将词表拼接为 initial_prompt 字符串，超限时从尾部截断"""
    if not terms:
        return ""
    text = " ".join(terms)
    if _estimate_tokens(text) <= _INITIAL_PROMPT_MAX_TOKENS:
        return text
    # 超限：从尾部逐个移除词条，直到 token 数达标
    trimmed = terms[:]
    while trimmed and _estimate_tokens(" ".join(trimmed)) > _INITIAL_PROMPT_MAX_TOKENS:
        trimmed.pop()
    return " ".join(trimmed)


class ASREngine:
    """语音识别引擎，基于 Faster-Whisper (CTranslate2)"""

    def __init__(self, model_name=None, device=None, compute_type=None):
        logger.info("正在初始化语音识别模型...")
        try:
            self.model = WhisperModel(
                model_name or config.WHISPER_MODEL,
                device=device or config.WHISPER_DEVICE,
                compute_type=compute_type or config.WHISPER_COMPUTE_TYPE,
            )
            logger.info("Faster-Whisper 模型加载完成")
        except Exception as e:
            logger.error("加载失败 %s，回退到 tiny 模型 + int8 量化", e)
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


    def transcribe_iter(self, audio_path, progress_callback=None, initial_prompt=None):
        duration_sec = _get_audio_duration(audio_path)
        beam_size = self._get_beam_size(duration_sec)

        segments_raw, info = self.model.transcribe(
            audio_path,
            language=config.WHISPER_LANGUAGE,
            beam_size=beam_size,
            vad_filter=False,
            condition_on_previous_text=True,
            initial_prompt=initial_prompt or "以下是普通话会议录音，请使用简体中文输出。",
        )

        total_est = int(info.duration / 5) + 1
        for idx, seg in enumerate(segments_raw):
            item = self._build_segment(idx, seg)
            if progress_callback:
                progress_callback(idx + 1, total_est)
            yield item, info.duration

    def transcribe(self, audio_path, progress_callback=None, initial_prompt=None):
        segments = []
        duration = 0.0
        for item, dur in self.transcribe_iter(audio_path, progress_callback, initial_prompt=initial_prompt):
            segments.append(item)
            duration = dur
        return segments, duration

    def transcribe_parallel_iter(self, audio_path):
        """Parallel chunked transcription for long audio.

        Yields dicts:
          {"type": "chunk_done", "completed": int, "total": int, "pct": int}
          {"type": "complete",   "segments": list}
        """
        duration_s = _get_audio_duration(audio_path)
        chunks, tmpdir = _split_audio_ffmpeg(audio_path, duration_s or _PARALLEL_MIN_SEC)
        n = len(chunks)
        n_workers = min(multiprocessing.cpu_count(), n, _MAX_WORKERS)
        logger.info("并行转写：%d 块，%d 进程", n, n_workers)

        tasks = [
            (
                c["index"], c["path"], c["start_s"],
                config.WHISPER_MODEL, config.WHISPER_DEVICE,
                config.WHISPER_COMPUTE_TYPE, config.WHISPER_LANGUAGE,
                "以下是普通话会议录音，请使用简体中文输出。",
            )
            for c in chunks
        ]

        results: dict = {}
        try:
            with ProcessPoolExecutor(max_workers=n_workers) as executor:
                futures = {executor.submit(_transcribe_chunk_worker, t): t[0] for t in tasks}
                for future in as_completed(futures):
                    r = future.result()
                    results[r["index"]] = r
                    completed = len(results)
                    if not r["success"]:
                        logger.warning("块 %d 转写失败: %s", r["index"], r.get("error"))
                    yield {
                        "type":      "chunk_done",
                        "completed": completed,
                        "total":     n,
                        "pct":       int(completed / n * 55),
                    }
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        all_segments = []
        for idx in sorted(results.keys()):
            r = results[idx]
            if r["success"]:
                all_segments.extend(r["segments"])
        all_segments.sort(key=lambda s: s["start"])
        yield {"type": "complete", "segments": all_segments}

    @staticmethod
    def classify_duration(duration):
        if duration < 300:
            return "short"
        elif duration < 1800:
            return "medium"
        return "long"

    @staticmethod
    def classify_meeting_type(duration, num_speakers, noise_level):
        return ASREngine.classify_duration(duration), "unknown"
