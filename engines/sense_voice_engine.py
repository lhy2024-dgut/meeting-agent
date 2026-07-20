"""FunASR / SenseVoiceSmall ASR 引擎。"""

import os
import re
import shutil
import tempfile
import time
from pathlib import Path

import config
from logger import get_logger

logger = get_logger(__name__)

_funasr_model = None

_MODELSCOPE_LOCAL = config.FUNASR_MODEL_DIR / "iic" / "SenseVoiceSmall"
_HF_LOCAL = (
    Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface" / "hub"))
    / "models--FunAudioLLM--SenseVoiceSmall"
    / "snapshots"
)


def _hf_snapshot_path() -> Path | None:
    if not _HF_LOCAL.exists():
        return None

    snapshots = sorted(_HF_LOCAL.iterdir())
    for snapshot in reversed(snapshots):
        if (snapshot / "model.pt").exists() or (snapshot / "config.yaml").exists():
            return snapshot
    return None


def _load_model():
    global _funasr_model
    if _funasr_model is not None:
        return _funasr_model
    logger.info("正在加载 SenseVoiceSmall 模型（首次加载约 30-60s）...")

    from funasr import AutoModel

    candidates: list[dict] = []
    if _MODELSCOPE_LOCAL.exists():
        candidates.append({"model": str(_MODELSCOPE_LOCAL)})
        logger.info("检测到 ModelScope 本地缓存：%s", _MODELSCOPE_LOCAL)

    hf_snapshot = _hf_snapshot_path()
    if hf_snapshot:
        candidates.append({"model": str(hf_snapshot)})
        logger.info("检测到 HuggingFace 本地缓存：%s", hf_snapshot)

    candidates += [
        {"model": "iic/SenseVoiceSmall"},
        {"model": "FunAudioLLM/SenseVoiceSmall", "hub": "hf"},
    ]
    last_err = None
    for kwargs in candidates:
        try:
            _funasr_model = AutoModel(
                trust_remote_code=True,
                device="cpu",
                disable_update=True,
                **kwargs,
            )
            logger.info("SenseVoiceSmall 加载完成（来源：%s）", kwargs["model"])
            return _funasr_model
        except Exception as exc:
            logger.warning("SenseVoiceSmall 加载失败（%s）: %s", kwargs["model"], exc)
            last_err = exc

    raise RuntimeError(
        "SenseVoiceSmall 所有来源均加载失败。"
        "请检查网络或手动下载：python -c "
        "\"from modelscope import snapshot_download; snapshot_download('iic/SenseVoiceSmall')\"\n"
        f"最后错误：{last_err}"
    ) from last_err


def _postprocess(text: str) -> str:
    """移除 SenseVoice 输出中的标签，只保留纯文本。"""
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess

        return rich_transcription_postprocess(text)
    except Exception:
        return re.sub(r"<\|[^|]+\|>", "", text).strip()


def _build_hotword(terms: list | None) -> str | None:
    if not terms:
        return None
    return " ".join(term.strip() for term in terms if term and term.strip())


def _transcribe_chunk(model, chunk_path: str, start_offset: float, hotword: str | None) -> list[dict]:
    """转写单个音频块并返回带绝对时间戳的 segment 列表。"""
    gen_kwargs = dict(
        input=chunk_path,
        cache={},
        language="zh",
        use_itn=True,
        batch_size_s=60,
    )
    if hotword:
        try:
            result = model.generate(**gen_kwargs, hotword=hotword)
        except TypeError:
            result = model.generate(**gen_kwargs)
    else:
        result = model.generate(**gen_kwargs)

    segments = []
    seg_id = 0
    for item in result or []:
        raw_text = item.get("text", "")
        text = _postprocess(raw_text)
        if not text.strip():
            continue

        timestamp = item.get("timestamp", [])
        if timestamp:
            start_s = start_offset + timestamp[0][0] / 1000.0
            end_s = start_offset + timestamp[-1][1] / 1000.0
        else:
            start_s = start_offset
            end_s = start_offset + 5.0

        segments.append(
            {
                "id": seg_id,
                "text": text,
                "start": start_s,
                "end": end_s,
                "duration": end_s - start_s,
                "timestamp": time.time(),
            }
        )
        seg_id += 1
    return segments


class SenseVoiceEngine:
    """FunASR SenseVoiceSmall 引擎，接口与 ASREngine 兼容。"""

    _DIRECT_MAX_SEC = 120

    def __init__(self):
        self._model = None

    @property
    def model(self):
        if self._model is None:
            self._model = _load_model()
        return self._model

    def transcribe_iter(self, audio_path, progress_callback=None, terms=None):
        from engines.asr_engine import _PARALLEL_MIN_SEC, _get_audio_duration, _split_audio_ffmpeg

        hotword = _build_hotword(terms)
        total_duration = _get_audio_duration(audio_path) or _PARALLEL_MIN_SEC

        if total_duration > self._DIRECT_MAX_SEC:
            logger.info(
                "音频时长 %.1fs > %ds，SenseVoice 改用顺序切块转写",
                total_duration,
                self._DIRECT_MAX_SEC,
            )
            chunks, tmpdir = _split_audio_ffmpeg(audio_path, total_duration)
            seg_id = 0
            try:
                for chunk in chunks:
                    segs = _transcribe_chunk(self.model, chunk["path"], chunk["start_s"], hotword)
                    if progress_callback:
                        progress_callback(int(chunk["end_s"]), int(total_duration))
                    for seg in segs:
                        seg["id"] = seg_id
                        seg_id += 1
                        yield seg, total_duration
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
            return

        gen_kwargs = dict(
            input=audio_path,
            cache={},
            language="zh",
            use_itn=True,
            batch_size_s=60,
            merge_vad=True,
            merge_length_s=15,
        )
        if hotword:
            try:
                result = self.model.generate(**gen_kwargs, hotword=hotword)
            except TypeError:
                result = self.model.generate(**gen_kwargs)
        else:
            result = self.model.generate(**gen_kwargs)

        seg_id = 0
        for item in result or []:
            text = _postprocess(item.get("text", ""))
            if not text.strip():
                continue
            timestamp = item.get("timestamp", [])
            if timestamp:
                start_s = timestamp[0][0] / 1000.0
                end_s = timestamp[-1][1] / 1000.0
            else:
                start_s = 0.0
                end_s = total_duration
            yield {
                "id": seg_id,
                "text": text,
                "start": start_s,
                "end": end_s,
                "duration": end_s - start_s,
                "timestamp": time.time(),
            }, total_duration
            seg_id += 1

        if progress_callback:
            progress_callback(1, 1)

    def transcribe(self, audio_path, progress_callback=None, terms=None):
        segments, duration = [], 0.0
        for seg, dur in self.transcribe_iter(audio_path, progress_callback, terms):
            segments.append(seg)
            duration = dur
        return segments, duration

    def transcribe_parallel_iter(self, audio_path, terms=None):
        from engines.asr_engine import _PARALLEL_MIN_SEC, _get_audio_duration, _split_audio_ffmpeg

        hotword = _build_hotword(terms)
        duration_s = _get_audio_duration(audio_path) or _PARALLEL_MIN_SEC
        chunks, tmpdir = _split_audio_ffmpeg(audio_path, duration_s)
        total = len(chunks)
        logger.info("SenseVoice 切块转写：%d 块", total)

        all_segments = []
        try:
            for idx, chunk in enumerate(chunks):
                segs = _transcribe_chunk(self.model, chunk["path"], chunk["start_s"], hotword)
                all_segments.extend(segs)
                completed = idx + 1
                yield {
                    "type": "chunk_done",
                    "completed": completed,
                    "total": total,
                    "pct": int(completed / total * 55),
                }
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        for new_id, seg in enumerate(all_segments):
            seg["id"] = new_id
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
    def classify_meeting_type(duration, num_speakers=None, noise_level=None):
        if num_speakers is not None and num_speakers >= 2:
            environment = "multi_speaker"
        else:
            environment = "unknown"
        return SenseVoiceEngine.classify_duration(duration), environment


_sv_engine_instance: SenseVoiceEngine | None = None


def get_sensevoice_engine() -> SenseVoiceEngine:
    """返回 SenseVoiceEngine 单例，避免重复加载模型。"""
    global _sv_engine_instance
    if _sv_engine_instance is None:
        _sv_engine_instance = SenseVoiceEngine()
    return _sv_engine_instance
