import hashlib
from datetime import datetime
from pathlib import Path

import config
from engines.audio_utils import extract_audio_from_video
from logger import get_logger

logger = get_logger(__name__)


class FileService:
    def __init__(self, audio_dir=None, video_dir=None, output_dir=None, template_dir=None):
        self.audio_dir = audio_dir or config.AUDIO_DIR
        self.video_dir = video_dir or config.VIDEO_DIR
        self.output_dir = output_dir or config.OUTPUT_DIR
        self.template_dir = template_dir or config.TEMPLATE_DIR

    def save_uploaded(self, uploaded_file, file_type="audio"):
        allowed_map = {
            "audio": set(config.ALLOWED_AUDIO_EXTENSIONS),
            "video": set(config.ALLOWED_VIDEO_EXTENSIONS),
            "template": set(config.ALLOWED_TEMPLATE_EXTENSIONS),
        }
        ext = Path(uploaded_file.name).suffix.lower()
        allowed = allowed_map.get(file_type, set())
        if allowed and ext not in allowed:
            raise ValueError(
                f"不支持的文件类型: {ext}，仅允许: {', '.join(sorted(allowed))}"
            )

        file_bytes = uploaded_file.getvalue()
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file_hash[:8]}{ext}"

        save_dir = {
            "audio": self.audio_dir,
            "video": self.video_dir,
            "template": self.template_dir,
        }.get(file_type, self.output_dir)

        path = save_dir / filename
        path.write_bytes(file_bytes)
        return str(path), file_hash

    def prepare_audio_path(self, file_path, ext):
        if ext in config.ALLOWED_VIDEO_EXTENSIONS:
            return extract_audio_from_video(file_path)
        return file_path
