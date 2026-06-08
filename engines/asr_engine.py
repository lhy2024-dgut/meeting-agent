import json
import subprocess
import time

from faster_whisper import WhisperModel

import config
from logger import get_logger

logger = get_logger(__name__)


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
        duration_sec, noise_level = _get_audio_info(audio_path)
        beam_size = self._get_beam_size(duration_sec)

        segments_raw, info = self.model.transcribe(
            audio_path,
            language=config.WHISPER_LANGUAGE,
            beam_size=beam_size,
            vad_filter=False,
            condition_on_previous_text=True,
            initial_prompt=initial_prompt,
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
