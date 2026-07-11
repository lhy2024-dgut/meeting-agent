import hashlib
import os
import shutil
import subprocess
import wave
from pathlib import Path


_FFMPEG_CANDIDATE_DIRS = [
    r"C:\ffmpeg\ffmpeg-master-latest-win64-gpl\bin",
    r"D:\ffmpeg\bin",
    r"C:\ffmpeg\bin",
    r"C:\Program Files\ffmpeg\bin",
    r"C:\ProgramData\chocolatey\bin",
]


def _find_ffmpeg() -> str:
    for directory in _FFMPEG_CANDIDATE_DIRS:
        path = os.path.join(directory, "ffmpeg.exe")
        if os.path.isfile(path):
            return path

    found = shutil.which("ffmpeg")
    if found:
        return found

    return "ffmpeg"


_FFMPEG = _find_ffmpeg()


def extract_audio_from_video(video_path):
    """从视频中提取音频（使用 ffmpeg）。"""
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


def convert_audio_to_wav(input_path, output_path=None, sample_rate=16000):
    """将任意 ffmpeg 支持的音频容器转为单声道 WAV。"""
    src = Path(input_path)
    dest = Path(output_path) if output_path else src.with_suffix(".wav")
    subprocess.run(
        [
            _FFMPEG,
            "-y",
            "-i",
            str(src),
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            str(dest),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return str(dest)


def concat_wav_files(input_paths, output_path):
    """拼接多个 WAV 片段为一个完整的 WAV。"""
    paths = [Path(item) for item in input_paths if item]
    if not paths:
        raise ValueError("No WAV chunks to concatenate")

    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(paths[0]), "rb") as first:
        params = first.getparams()
        frames = [first.readframes(first.getnframes())]

    for path in paths[1:]:
        with wave.open(str(path), "rb") as handle:
            if (
                handle.getnchannels() != params.nchannels
                or handle.getsampwidth() != params.sampwidth
                or handle.getframerate() != params.framerate
            ):
                raise ValueError(f"Incompatible WAV chunk: {path}")
            frames.append(handle.readframes(handle.getnframes()))

    with wave.open(str(dest), "wb") as out:
        out.setparams(params)
        for frame in frames:
            out.writeframes(frame)
    return str(dest)


def compute_file_hash(file_bytes):
    return hashlib.sha256(file_bytes).hexdigest()
