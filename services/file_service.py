import hashlib
from datetime import datetime
from pathlib import Path

import config
from engines.audio_utils import extract_audio_from_video


class FileService:
    def __init__(self):
        self.audio_dir = config.AUDIO_DIR
        self.video_dir = config.VIDEO_DIR
        self.output_dir = config.OUTPUT_DIR
        self.template_dir = config.TEMPLATE_DIR

    def save_uploaded(self, uploaded_file, file_type="audio"):
        file_bytes = uploaded_file.getvalue()
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = Path(uploaded_file.name).suffix.lower()
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
