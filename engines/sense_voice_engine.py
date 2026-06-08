"""FunASR / SenseVoiceSmall ASR 引擎

与 ASREngine（faster-whisper）暴露相同接口：
  transcribe_iter(audio_path, progress_callback, terms)
  transcribe_parallel_iter(audio_path, terms)
  transcribe(audio_path, progress_callback, terms)
  classify_duration(duration)

时间戳策略：
  SenseVoice 通过 AutoModel+vad_model 时仅返回合并文本，无每句时间戳。
  因此复用 asr_engine._split_audio_ffmpeg 在静音处切块，对每块独立
  调用 SenseVoice 进行转写，由切块的起止时间提供准确的 segment 时间戳。
  这与 faster-whisper 并行模式一致，保证下游 pipeline 兼容。
"""

import re
import shutil
import tempfile
import time

from logger import get_logger

logger = get_logger(__name__)

# ── 延迟导入 funasr ──────────────────────────────────────────────────────────
_funasr_model = None


def _load_model():
    global _funasr_model
    if _funasr_model is not None:
        return _funasr_model
    logger.info("正在加载 SenseVoiceSmall 模型（首次加载约 30-60s）...")

    from funasr import AutoModel

    _CANDIDATES = [
        {"model": "iic/SenseVoiceSmall"},                          # ModelScope（国内首选）
        {"model": "FunAudioLLM/SenseVoiceSmall", "hub": "hf"},     # HuggingFace
    ]
    last_err = None
    for kwargs in _CANDIDATES:
        try:
            _funasr_model = AutoModel(
                trust_remote_code=True,
                device="cpu",
                disable_update=True,
                **kwargs,
            )
            logger.info("SenseVoiceSmall 加载完成（来源：%s）", kwargs["model"])
            return _funasr_model
        except Exception as e:
            logger.warning("SenseVoiceSmall 加载失败（%s）: %s", kwargs["model"], e)
            last_err = e

    raise RuntimeError(
        "SenseVoiceSmall 所有来源均加载失败。"
        "请检查网络或手动下载：python -c "
        "\"from modelscope import snapshot_download; snapshot_download('iic/SenseVoiceSmall')\"\n"
        f"最后错误：{last_err}"
    ) from last_err


def _postprocess(text: str) -> str:
    """去除 SenseVoice 输出的情感/事件标签，返回纯文本"""
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
        return rich_transcription_postprocess(text)
    except Exception:
        return re.sub(r"<\|[^|]+\|>", "", text).strip()


def _build_hotword(terms: list | None) -> str | None:
    if not terms:
        return None
    return " ".join(t.strip() for t in terms if t.strip())


def _transcribe_chunk(model, chunk_path: str, start_offset: float,
                      hotword: str | None) -> list[dict]:
    """用 SenseVoice 转写单个音频块，返回带绝对时间戳的 segment 列表"""
    gen_kwargs = dict(
        input=chunk_path,
        cache={},
        language="zh",
        use_itn=True,
        batch_size_s=300,
    )
    if hotword:
        try:
            res = model.generate(**gen_kwargs, hotword=hotword)
        except TypeError:
            res = model.generate(**gen_kwargs)
    else:
        res = model.generate(**gen_kwargs)

    segments = []
    seg_id = 0
    for item in (res or []):
        raw_text = item.get("text", "")
        text = _postprocess(raw_text)
        if not text.strip():
            continue

        # 尝试从字符级时间戳中获取句子起止（单位 ms）
        ts = item.get("timestamp", [])
        if ts:
            start_s = start_offset + ts[0][0] / 1000.0
            end_s = start_offset + ts[-1][1] / 1000.0
        else:
            # 无时间戳：用 VAD 块的起止时间作为粗粒度估算
            start_s = start_offset
            end_s = start_offset + 5.0  # 最差情况：每块标 5s

        segments.append({
            "id": seg_id,
            "text": text,
            "start": start_s,
            "end": end_s,
            "duration": end_s - start_s,
            "timestamp": time.time(),
        })
        seg_id += 1
    return segments


class SenseVoiceEngine:
    """FunASR SenseVoiceSmall 引擎，接口与 ASREngine（faster-whisper）兼容

    直接转写（transcribe_iter）：整段音频送入模型，只有一个 FunASR 进度条。
    并行转写（transcribe_parallel_iter）：ffmpeg 切块后逐块处理，进度更细。
    """

    def __init__(self):
        self._model = None

    @property
    def model(self):
        if self._model is None:
            self._model = _load_model()
        return self._model

    # ── 主接口 ────────────────────────────────────────────────────────────────

    def transcribe_iter(self, audio_path, progress_callback=None, terms=None):
        """直接转写：整段音频送入 SenseVoice，不切块，只产生一个 FunASR 进度条。

        时间戳粒度较粗（整段 start=0, end=duration），适合快速对比评测场景。
        Yields: (segment_dict, total_duration)
        """
        from engines.asr_engine import _get_audio_duration, _PARALLEL_MIN_SEC
        hotword = _build_hotword(terms)
        total_duration = _get_audio_duration(audio_path) or _PARALLEL_MIN_SEC

        gen_kwargs = dict(
            input=audio_path,
            cache={},
            language="zh",
            use_itn=True,
            batch_size_s=300,
            merge_vad=True,
            merge_length_s=30,
        )
        if hotword:
            try:
                res = self.model.generate(**gen_kwargs, hotword=hotword)
            except TypeError:
                res = self.model.generate(**gen_kwargs)
        else:
            res = self.model.generate(**gen_kwargs)

        # 整段 → 合并所有结果为一个 segment（或按 FunASR VAD 分段）
        all_segments = []
        seg_id = 0
        for item in (res or []):
            text = _postprocess(item.get("text", ""))
            if not text.strip():
                continue
            all_segments.append({
                "id": seg_id,
                "text": text,
                "start": 0.0,
                "end": total_duration,
                "duration": total_duration,
                "timestamp": time.time(),
            })
            seg_id += 1

        if progress_callback:
            progress_callback(1, 1)

        for seg in all_segments:
            yield seg, total_duration

    def transcribe(self, audio_path, progress_callback=None, terms=None):
        """同步转写，返回 (segments, duration)"""
        segments, duration = [], 0.0
        for seg, dur in self.transcribe_iter(audio_path, progress_callback, terms):
            segments.append(seg)
            duration = dur
        return segments, duration

    def transcribe_parallel_iter(self, audio_path, terms=None):
        """并行（切块）转写：ffmpeg 静音切块后逐块处理，时间戳更精确。

        Yields progress events: chunk_done / complete
        """
        from engines.asr_engine import _get_audio_duration, _split_audio_ffmpeg, _PARALLEL_MIN_SEC
        hotword = _build_hotword(terms)
        duration_s = _get_audio_duration(audio_path) or _PARALLEL_MIN_SEC
        chunks, tmpdir = _split_audio_ffmpeg(audio_path, duration_s)
        n = len(chunks)
        logger.info("SenseVoice 切块转写：%d 块", n)

        all_segments = []
        try:
            for i, chunk in enumerate(chunks):
                segs = _transcribe_chunk(self.model, chunk["path"], chunk["start_s"], hotword)
                all_segments.extend(segs)
                completed = i + 1
                yield {
                    "type": "chunk_done",
                    "completed": completed,
                    "total": n,
                    "pct": int(completed / n * 55),
                }
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        for new_id, seg in enumerate(all_segments):
            seg["id"] = new_id
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
    def classify_meeting_type(duration, num_speakers=1, noise_level=0.3):
        return SenseVoiceEngine.classify_duration(duration), "unknown"


# ── 模块级单例（Fix 2：避免每次重复加载模型）───────────────────────────────────

_sv_engine_instance: SenseVoiceEngine | None = None


def get_sensevoice_engine() -> SenseVoiceEngine:
    """返回 SenseVoiceEngine 单例，模型只加载一次"""
    global _sv_engine_instance
    if _sv_engine_instance is None:
        _sv_engine_instance = SenseVoiceEngine()
    return _sv_engine_instance
