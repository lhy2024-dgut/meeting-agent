import hashlib
import os
import shutil
import subprocess
from pathlib import Path


def _find_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for d in [r"D:\ffmpeg\bin", r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin"]:
        p = os.path.join(d, "ffmpeg.exe")
        if os.path.isfile(p):
            return p
    return "ffmpeg"


_FFMPEG = _find_ffmpeg()


def extract_audio_from_video(video_path):
    """从视频中提取音频（使用 ffmpeg）"""
    output_path = Path(video_path).with_suffix(".wav")
    if output_path.exists():
        return str(output_path)
    subprocess.run(
        [
            _FFMPEG,
            "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            str(output_path),
        ],
        check=True,
    )
    return str(output_path)


def compute_file_hash(file_bytes):
    return hashlib.sha256(file_bytes).hexdigest()
