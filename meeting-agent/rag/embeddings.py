# -*- coding: utf-8 -*-
"""Ollama-based Embedding — 替代 onnxruntime/sentence-transformers，零崩溃风险"""

from typing import Optional

from langchain_core.embeddings import Embeddings

import config


def _sanitize_text(text):
    """移除 Windows 下可能产生的 surrogate 字符，防止 UTF-8 编码失败"""
    if not text:
        return ""
    if isinstance(text, str):
        cleaned = []
        for ch in text:
            cp = ord(ch)
            if 0xD800 <= cp <= 0xDFFF:
                continue
            cleaned.append(ch)
        return "".join(cleaned)
    return str(text)


_embedding_model: Optional["OllamaEmbeddings"] = None


class OllamaEmbeddings(Embeddings):
    """LangChain 兼容的 Ollama Embedding 封装"""

    def __init__(self, model: str = "bge-m3", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self._client = None
        print(f"[OK] Ollama Embedding 就绪: {self.model}")

    @property
    def client(self):
        if self._client is None:
            import ollama

            self._client = ollama.Client(host=self.base_url)
        return self._client

    def __call__(self, text: str) -> list[float]:
        """兼容旧版 FAISS wrapper 的函数式调用"""
        return self.embed_query(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量文本转向量"""
        vectors = []
        for text in texts:
            text = _sanitize_text(text)
            resp = self.client.embed(model=self.model, input=text)
            vectors.append(resp.embeddings[0])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """单条查询转向量"""
        text = _sanitize_text(text)
        resp = self.client.embed(model=self.model, input=text)
        return resp.embeddings[0]


def get_embeddings() -> OllamaEmbeddings:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = OllamaEmbeddings(
            model=config.EMBEDDING_MODEL,
            base_url=config.OLLAMA_BASE_URL,
        )
    return _embedding_model


def load_or_create_faiss(embeddings: OllamaEmbeddings):
    """加载已有 FAISS 索引，不存在则创建空库"""
    from langchain_community.vectorstores import FAISS

    index_path = config.VECTOR_STORE_DIR / "meeting_kb.faiss"
    if index_path.exists():
        print("[OK] 加载已有 FAISS 向量索引")
        return FAISS.load_local(
            str(config.VECTOR_STORE_DIR),
            embeddings,
            index_name="meeting_kb",
            allow_dangerous_deserialization=True,
        )
    print("[OK] 创建新 FAISS 向量库")
    return FAISS.from_texts(["__init__"], embeddings)
