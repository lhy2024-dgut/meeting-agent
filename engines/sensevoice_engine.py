# -*- coding: utf-8 -*-
"""SenseVoice ASR 引擎 — 阿里 FunAudioLLM 开源，中文效果远超 Whisper

模型: SenseVoiceSmall (244M 参数)
优势:
  - 中文 CER 比 Whisper-large-v3 低 2~4 倍
  - 推理速度比 Whisper-large-v3 快 15 倍
  - 自带 VAD + 标点恢复 + 时间戳
  - CPU 完全可用
"""

import re
import time

from logger import get_logger

logger = get_logger(__name__)

_model = None


def _clean_sensevoice_text(text: str) -> str:
    """清理 SenseVoice 输出中的特殊标签

    SenseVoice 输出格式: <|zh|><|EMO_UNKNOWN|><|Speech|><|withitn|>实际文本<|zh|><|NEUTRAL|><|Speech|><|withitn|>更多文本
    需要提取纯文本
    """
    # 移除所有 <|...|> 标签
    cleaned = re.sub(r'<\|[^|]*\|>', '', text)
    # 清理多余空格
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _load_model():
    global _model
    if _model is None:
        from funasr import AutoModel
        logger.info("正在加载 SenseVoice-Small 模型...")
        _model = AutoModel(
            model="iic/SenseVoiceSmall",
            vad_model="fsmn-vad",       # 内置 VAD
            vad_kwargs={"max_single_segment_time": 30000},  # 最大 30 秒一段
            trust_remote_code=True,
        )
        logger.info("SenseVoice-Small 模型加载完成")
    return _model


def _get_audio_duration(audio_path: str) -> float:
    """用 ffprobe 获取音频时长"""
    import json
    import subprocess
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
            capture_output=True, text=True, timeout=30,
        )
        info = json.loads(result.stdout)
        return float(info.get("format", {}).get("duration", 0))
    except Exception:
        return 0


class SenseVoiceEngine:
    """SenseVoice ASR 引擎，接口与 ASREngine 兼容"""

    def __init__(self):
        _load_model()

    def transcribe(self, audio_path: str, progress_callback=None) -> tuple[list, float]:
        """转写音频，返回 (segments, duration)

        segments: [{"id": int, "text": str, "start": float, "end": float, "duration": float}, ...]
        duration: 音频总时长(秒)
        """
        segments = []
        duration = 0.0
        for item, dur in self.transcribe_iter(audio_path, progress_callback):
            segments.append(item)
            duration = dur
        return segments, duration

    def transcribe_iter(self, audio_path: str, progress_callback=None):
        """流式转写，yield (segment, duration)"""
        model = _load_model()

        # 先获取音频真实时长
        total_duration = _get_audio_duration(audio_path)

        t0 = time.time()
        result = model.generate(
            input=audio_path,
            cache={},
            language="auto",         # 自动语言检测
            use_itn=True,            # 逆文本归一化（数字、日期）
            batch_size_s=60,         # 每批 60 秒
            merge_vad=True,          # 合并 VAD 片段
            merge_length_s=15,       # 合并到 15 秒
        )
        elapsed = time.time() - t0

        # 解析结果
        if not result:
            yield {}, total_duration
            return

        # FunASR 返回格式: [{"key": ..., "text": ..., "timestamp": [[s,e], ...], "sentence_info": [...]}]
        for item in result:
            text = item.get("text", "")
            text = _clean_sensevoice_text(text)  # 清理特殊标签
            sentences = item.get("sentence_info", [])

            if sentences:
                # 有句子级时间戳
                for i, sent in enumerate(sentences):
                    sent_text = _clean_sensevoice_text(sent.get("text", ""))
                    seg = {
                        "id": i,
                        "text": sent_text.strip(),
                        "start": sent.get("start", 0) / 1000.0,  # ms → s
                        "end": sent.get("end", 0) / 1000.0,
                        "duration": (sent.get("end", 0) - sent.get("start", 0)) / 1000.0,
                        "timestamp": time.time(),
                    }
                    duration_sec = sent.get("end", 0) / 1000.0
                    if progress_callback:
                        progress_callback(i + 1, len(sentences))
                    yield seg, duration_sec
            else:
                # 无句子级时间戳，整段返回
                timestamp = item.get("timestamp", [])
                start = timestamp[0][0] / 1000.0 if timestamp else 0
                end = timestamp[-1][1] / 1000.0 if timestamp else total_duration
                seg = {
                    "id": 0,
                    "text": text.strip(),
                    "start": start,
                    "end": end,
                    "duration": end - start,
                    "timestamp": time.time(),
                }
                yield seg, total_duration or end

    @staticmethod
    def classify_duration(duration):
        if duration < 300:
            return "short"
        elif duration < 1800:
            return "medium"
        return "long"
