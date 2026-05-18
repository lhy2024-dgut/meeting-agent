import time

from faster_whisper import WhisperModel
from pydub import AudioSegment

import config


class ASREngine:
    """语音识别引擎，基于 Faster-Whisper (CTranslate2)"""

    def __init__(self):
        print("正在初始化语音识别模型...")
        try:
            self.model = WhisperModel(
                config.WHISPER_MODEL,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE_TYPE,
            )
            print("[OK] Faster-Whisper 模型加载完成")
        except Exception as e:
            print(f"加载失败 {e}，回退到 tiny 模型 + int8 量化")
            self.model = WhisperModel("tiny", device="cpu", compute_type="int8")

    def _get_audio_info(self, audio_path):
        try:
            audio = AudioSegment.from_file(audio_path)
            duration_sec = len(audio) / 1000.0
            dbfs = audio.dBFS
            noise_level = min(1.0, max(0.0, (dbfs + 30) / 25))
        except Exception:
            duration_sec = 0
            noise_level = 0.3
        return duration_sec, noise_level

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

    def transcribe_iter(self, audio_path, progress_callback=None):
        """生成器：逐 segment 返回识别结果，支持实时消费"""
        duration_sec, noise_level = self._get_audio_info(audio_path)
        beam_size = self._get_beam_size(duration_sec)

        segments_raw, info = self.model.transcribe(
            audio_path,
            language="zh",
            beam_size=beam_size,
            vad_filter=False,
            condition_on_previous_text=True,
        )

        total_est = int(info.duration / 5) + 1
        for idx, seg in enumerate(segments_raw):
            item = self._build_segment(idx, seg)
            if progress_callback:
                progress_callback(idx + 1, total_est)
            yield item, info.duration

    def transcribe(self, audio_path, progress_callback=None):
        """批量转写：收集所有 segment 后返回列表"""
        segments = []
        duration = 0.0
        for item, dur in self.transcribe_iter(audio_path, progress_callback):
            segments.append(item)
            duration = dur
        return segments, duration

    @staticmethod
    def classify_meeting_type(duration, num_speakers, noise_level):
        if duration < 300:
            dur = "short"
        elif duration < 1800:
            dur = "medium"
        else:
            dur = "long"

        if num_speakers > 3:
            env = "multi_speaker"
        elif noise_level > 0.5:
            env = "noisy"
        else:
            env = "quiet"
        return dur, env
