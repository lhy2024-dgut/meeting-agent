import os
import time
from faster_whisper import WhisperModel
from dotenv import load_dotenv

load_dotenv()

_model = None

def _get_model():
    global _model
    if _model is None:
        model_name = os.getenv("WHISPER_MODEL", "base")
        print(f"[ASR] 加载 faster-whisper {model_name} 模型...")
        t = time.time()
        # device="cpu", compute_type="int8" 是CPU下最快的组合
        _model = WhisperModel(model_name, device="cpu", compute_type="int8")
        print(f"[ASR] 模型加载完成，耗时 {time.time()-t:.1f}s")
    return _model

def transcribe(audio_path: str) -> dict:
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在：{audio_path}")

    model = _get_model()
    print(f"[ASR] 开始识别：{audio_path}")
    t = time.time()

    segments_gen, info = model.transcribe(
        audio_path,
        language="zh",
        # 关键：引导模型输出简体中文
        initial_prompt="以下是普通话会议录音，请使用简体中文输出。",
        beam_size=5
    )

    # faster-whisper 返回的是生成器，需要手动迭代
    segments = []
    full_text_parts = []
    for seg in segments_gen:
        segments.append({
            "text":  seg.text.strip(),
            "start": seg.start,
            "end":   seg.end,
            "id":    seg.id
        })
        full_text_parts.append(seg.text.strip())

    text = "\n".join(full_text_parts)  # 按句分段，解决无分段问题
    asr_time = time.time() - t

    print(f"[ASR] 识别完成：{len(text)} 字，{len(segments)} 段，耗时 {asr_time:.1f}s")
    return {
        "text":     text,
        "segments": segments,
        "language": info.language,
        "asr_time": asr_time
    }