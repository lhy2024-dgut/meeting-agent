# -*- coding: utf-8 -*-
"""RAG 检索器 — 基于 Ollama bge-m3 + FAISS"""

import config

_retriever_instance = None


def get_retriever():
    global _retriever_instance
    if _retriever_instance is None:
        try:
            from rag.embeddings import get_embeddings, load_or_create_faiss

            _retriever_instance = Retriever(get_embeddings(), load_or_create_faiss)
        except Exception as e:
            print(f"[WARN] RAG 初始化失败，知识库功能暂不可用: {e}")
            _retriever_instance = DummyRetriever()
    return _retriever_instance


class DummyRetriever:
    """RAG 不可用时的占位实现"""

    def index_meeting(self, *args, **kwargs):
        pass

    def search(self, query, top_k=5):
        return []

    def build_context(self, query, top_k=5):
        return ""


class Retriever:
    """基于 LangChain FAISS 的 RAG 检索器"""

    def __init__(self, embeddings, store_factory):
        from rag.text_splitter import SimpleTextSplitter

        self.embeddings = embeddings
        self.store = store_factory(embeddings)
        self.splitter = SimpleTextSplitter(
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )

    def index_meeting(
        self, meeting_id, transcript="", minutes="", action_items="", resolutions=""
    ):
        texts_to_index = []
        if transcript:
            texts_to_index.append(transcript)
        if minutes:
            texts_to_index.append(minutes)
        if action_items:
            texts_to_index.append(action_items)
        if resolutions:
            texts_to_index.append(resolutions)

        all_docs = []
        for text in texts_to_index:
            if not text or not text.strip():
                continue
            chunks = self.splitter.split_text(text)
            for chunk in chunks:
                all_docs.append(f"[meeting:{meeting_id}] {chunk}")

        if not all_docs:
            return

        self.store.add_texts(all_docs)
        self.store.save_local(str(config.VECTOR_STORE_DIR), index_name="meeting_kb")
        print(f"[OK] 会议 {meeting_id} 已索引到知识库，共 {len(all_docs)} 个片段")

    def search(self, query, top_k=5):
        docs_with_scores = self.store.similarity_search_with_score(query, k=top_k)
        results = [
            {"score": float(score), "text": doc.page_content}
            for doc, score in docs_with_scores
        ]
        # 若相关度都偏低，扩大检索范围
        if results and all(r["score"] < 0.3 for r in results):
            docs_with_scores = self.store.similarity_search_with_score(query, k=top_k * 2)
            results = [
                {"score": float(score), "text": doc.page_content}
                for doc, score in docs_with_scores
            ]
        return results

    def build_context(self, query, top_k=5):
        results = self.search(query, top_k=top_k)
        if not results:
            return ""
        return "\n\n".join(f"[相关度: {r['score']:.2f}] {r['text']}" for r in results)
