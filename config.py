import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")
STORAGE_DIR = ROOT_DIR / "storage"
STORAGE_DIR.mkdir(exist_ok=True)
(AUDIO_DIR := STORAGE_DIR / "audio").mkdir(exist_ok=True)
(VIDEO_DIR := STORAGE_DIR / "video").mkdir(exist_ok=True)
(TEMPLATE_DIR := STORAGE_DIR / "templates").mkdir(exist_ok=True)
(OUTPUT_DIR := STORAGE_DIR / "output").mkdir(exist_ok=True)

# Database (PostgreSQL)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "meeting_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")  # 必须设置环境变量

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

# LLM (Ollama)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5:4b")

# ASR (Faster-Whisper)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "zh")

# File support
ALLOWED_AUDIO_EXTENSIONS = [".wav", ".mp3", ".m4a", ".ogg", ".flac"]
ALLOWED_VIDEO_EXTENSIONS = [".mp4", ".avi", ".mov", ".mkv"]
ALLOWED_TEMPLATE_EXTENSIONS = [".docx", ".md", ".pdf"]

# RAG
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64

# Labels
DURATION_LABELS = {"short": "短会", "medium": "中等", "long": "长会"}
ENV_LABELS = {"quiet": "安静", "noisy": "嘈杂", "multi_speaker": "多人"}
