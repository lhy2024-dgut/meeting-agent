import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
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
DB_PASS = os.getenv("DB_PASS", "123456")

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

# File support
ALLOWED_AUDIO_EXTENSIONS = [".wav", ".mp3", ".m4a", ".ogg", ".flac"]
ALLOWED_VIDEO_EXTENSIONS = [".mp4", ".avi", ".mov", ".mkv"]
ALLOWED_TEMPLATE_EXTENSIONS = [".docx", ".md", ".pdf"]

# RAG
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
VECTOR_STORE_DIR = ROOT_DIR / "storage" / "vector_store"
VECTOR_STORE_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Custom LLM wrapper — workaround for langchain-ollama 1.1.0 response parsing bug
# ---------------------------------------------------------------------------
from typing import Any, Iterator, Optional, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr


def _sanitize_text(text):
    """移除 Windows 下 Ollama 可能产生的 surrogate 字符，防止 UTF-8 编码失败"""
    if not text:
        return ""
    # 过滤掉 Unicode surrogate 范围 (U+D800–U+DFFF) 的字符
    if isinstance(text, str):
        cleaned = []
        for ch in text:
            cp = ord(ch)
            if 0xD800 <= cp <= 0xDFFF:
                continue
            cleaned.append(ch)
        return "".join(cleaned)
    return str(text)


class OllamaChatModel(BaseChatModel):
    """直接封装 ollama 库的 LangChain ChatModel，绕过 langchain-ollama 的解析 bug"""

    model: str = Field(default="qwen3.5:4b")
    base_url: str = Field(default="http://localhost:11434")
    temperature: float = Field(default=0.1)
    num_predict: int = Field(default=4096)
    _client: Any = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        import ollama as _ollama

        self._client = _ollama.Client(host=self.base_url)

    def _convert_messages(self, messages: Sequence[BaseMessage]) -> list[dict]:
        """将 LangChain 消息转为 ollama 格式"""
        converted = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                converted.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                converted.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                converted.append({"role": "assistant", "content": msg.content})
            else:
                converted.append({"role": "user", "content": str(msg.content)})
        return converted

    def _generate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs,
    ) -> ChatResult:
        ollama_messages = self._convert_messages(messages)
        options = {
            "temperature": self.temperature,
            "num_predict": self.num_predict,
        }
        if stop:
            options["stop"] = stop
        try:
            response = self._client.chat(
                model=self.model,
                messages=ollama_messages,
                options=options,
                think=False,
            )
            content = _sanitize_text(response.message.content or "")
        except Exception as e:
            content = f"[LLM Error: {e}]"

        message = AIMessage(content=content)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    def _stream(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs,
    ) -> Iterator[ChatGeneration]:
        ollama_messages = self._convert_messages(messages)
        options = {
            "temperature": self.temperature,
            "num_predict": self.num_predict,
        }
        if stop:
            options["stop"] = stop
        try:
            stream = self._client.chat(
                model=self.model,
                messages=ollama_messages,
                options=options,
                think=False,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.get("message", {}).get("content", "")
                if delta:
                    yield ChatGeneration(message=AIMessage(content=_sanitize_text(delta)))
        except Exception as e:
            yield ChatGeneration(message=AIMessage(content=f"[LLM Error: {e}]"))

    @property
    def _llm_type(self) -> str:
        return "ollama-chat"

    @property
    def _identifying_params(self) -> dict:
        return {"model": self.model, "temperature": self.temperature}


def get_llm(temperature=0.1):
    """返回自定义 OllamaChatModel 实例（绕过 langchain-ollama 解析 bug）"""
    return OllamaChatModel(
        model=LLM_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
        num_predict=4096,
    )
