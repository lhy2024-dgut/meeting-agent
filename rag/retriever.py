"""RAG 检索器 — PGVector + 动态 embedding 维度 + 依赖注入"""

from sqlalchemy import text

import config
from db.engine import get_engine
from logger import get_logger

logger = get_logger(__name__)

_retriever_instance = None


def get_retriever(embeddings=None):
    """返回 Retriever 实例，支持依赖注入"""
    global _retriever_instance
    if embeddings:
        try:
            return Retriever(embeddings)
        except Exception as e:
            logger.warning("RAG 初始化失败（注入的 embedding）: %s", e)
            return DummyRetriever()
    if _retriever_instance is None:
        try:
            from rag.embeddings import get_embeddings
            _retriever_instance = Retriever(get_embeddings())
        except Exception as e:
            logger.warning("RAG 初始化失败，知识库功能暂不可用: %s", e)
            _retriever_instance = DummyRetriever()
    return _retriever_instance


class DummyRetriever:
    def index_meeting(self, *args, **kwargs):
        pass

    def search(self, query, top_k=5, exclude_meeting_id=None):
        return []

    def remove_meeting(self, meeting_id):
        pass

    def build_context(self, query, top_k=5, exclude_meeting_id=None):
        return ""


class Retriever:
    """基于 PGVector 的 RAG 检索器"""

    def __init__(self, embeddings):
        from rag.text_splitter import SimpleTextSplitter

        self.embeddings = embeddings
        self.engine = get_engine()
        self.splitter = SimpleTextSplitter(
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )

    def index_meeting(self, meeting_id, transcript="", minutes="", action_items="", resolutions=""):
        texts = [t for t in [transcript, minutes, action_items, resolutions] if t and t.strip()]
        all_chunks = []
        for text in texts:
            all_chunks.extend(self.splitter.split_text(text))

        if not all_chunks:
            return

        vectors = self.embeddings.embed_documents(all_chunks)

        with self.engine.connect() as conn:
            for chunk, vec in zip(all_chunks, vectors):
                conn.execute(
                    text("INSERT INTO meeting_chunks (meeting_id, chunk_text, embedding) VALUES (:mid, :text, :vec)"),
                    {"mid": meeting_id, "text": chunk, "vec": vec},
                )
            conn.commit()
        logger.info("会议 %s 已索引到知识库，共 %s 个片段", meeting_id, len(all_chunks))

    def search(self, query, top_k=5, exclude_meeting_id=None):
        vec = self.embeddings.embed_query(query)

        if exclude_meeting_id:
            sql = text("""
                SELECT chunk_text, 1 - (embedding <=> :vec) AS similarity
                FROM meeting_chunks
                WHERE meeting_id != :exclude_id
                ORDER BY embedding <=> :vec
                LIMIT :k
            """)
            params = {"vec": vec, "exclude_id": exclude_meeting_id, "k": top_k}
        else:
            sql = text("""
                SELECT chunk_text, 1 - (embedding <=> :vec) AS similarity
                FROM meeting_chunks
                ORDER BY embedding <=> :vec
                LIMIT :k
            """)
            params = {"vec": vec, "k": top_k}

        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [{"score": round(row[1], 4), "text": row[0]} for row in rows]

    def remove_meeting(self, meeting_id):
        with self.engine.connect() as conn:
            result = conn.execute(
                text("DELETE FROM meeting_chunks WHERE meeting_id = :mid"),
                {"mid": meeting_id},
            )
            conn.commit()
            if result.rowcount:
                logger.info("已从知识库移除会议 %s 的 %s 个片段", meeting_id, result.rowcount)

    def build_context(self, query, top_k=5, exclude_meeting_id=None):
        results = self.search(query, top_k=top_k, exclude_meeting_id=exclude_meeting_id)
        if not results:
            return ""
        return "\n\n".join(f"[余弦相似度: {r['score']:.3f}] {r['text']}" for r in results)
