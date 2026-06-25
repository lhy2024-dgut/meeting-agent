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

# Auth
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-secret-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
DEFAULT_ADMIN_USERNAME = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "ChangeMe123!")
DEFAULT_ADMIN_DISPLAY_NAME = os.getenv("DEFAULT_ADMIN_DISPLAY_NAME", "Administrator")

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

# Chunk 切分策略: "fixed_512" | "segment_300" | "semantic"
CHUNK_STRATEGY_FIXED    = "fixed_512"    # 现有固定 512 字切分
CHUNK_STRATEGY_SEGMENT  = "segment_300"  # ASR segments 合并至 300 字
CHUNK_STRATEGY_SEMANTIC = "semantic"     # 基于 embedding 语义相似度切分

# RAG 检索模式: "vector" | "bm25" | "hybrid"
SEARCH_MODE = os.getenv("SEARCH_MODE", "hybrid")
# Reranker 开关
RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
# Reranker 模型
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
# 分数阈值：过滤弱相关结果，0 表示不过滤
MIN_SCORE_THRESHOLD = float(os.getenv("MIN_SCORE_THRESHOLD", "0"))
MIN_RERANK_SCORE = float(os.getenv("MIN_RERANK_SCORE", "0"))
# Hybrid 检索召回宽度倍数
RECALL_MULTIPLIER = int(os.getenv("RECALL_MULTIPLIER", "4"))

# Labels
DURATION_LABELS = {"short": "短会", "medium": "中等", "long": "长会"}
ENV_LABELS = {"quiet": "安静", "noisy": "嘈杂", "multi_speaker": "多人"}
