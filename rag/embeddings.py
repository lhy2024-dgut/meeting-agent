"""Ollama-based Embedding — 批量请求 + 依赖注入"""

import threading
from typing import Optional

from langchain_core.embeddings import Embeddings

import config
from logger import get_logger
from utils import sanitize_text

logger = get_logger(__name__)

_embedding_model: Optional["OllamaEmbeddings"] = None
_embedding_lock = threading.Lock()


class OllamaEmbeddings(Embeddings):
    """LangChain 兼容的 Ollama Embedding 封装"""

    def __init__(self, model: str = "bge-m3", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self._client = None
        logger.info("Ollama Embedding 就绪: %s", self.model)

    @property
    def client(self):
        if self._client is None:
            import ollama
            self._client = ollama.Client(host=self.base_url)
        return self._client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        results = []
        batch_size = 50
        for i in range(0, len(texts), batch_size):
            batch = [sanitize_text(t) for t in texts[i:i + batch_size]]
            resp = self.client.embed(model=self.model, input=batch)
            results.extend(resp.embeddings)
        return results

    def embed_query(self, text: str) -> list[float]:
        text = sanitize_text(text)
        resp = self.client.embed(model=self.model, input=text)
        return resp.embeddings[0]


def get_embeddings(model=None, base_url=None):
    """返回 OllamaEmbeddings 实例，支持依赖注入（双重检查锁定，线程安全）"""
    global _embedding_model
    if model or base_url:
        return OllamaEmbeddings(
            model=model or config.EMBEDDING_MODEL,
            base_url=base_url or config.OLLAMA_BASE_URL,
        )
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:
                _embedding_model = OllamaEmbeddings(
                    model=config.EMBEDDING_MODEL,
                    base_url=config.OLLAMA_BASE_URL,
                )
    return _embedding_model
