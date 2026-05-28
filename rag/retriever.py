"""RAG 检索器 — PGVector + 覆盖式索引 + 结构化 chunk + 依赖注入"""

import hashlib
from datetime import datetime

from sqlalchemy import text

import config
from db.engine import get_engine
from logger import get_logger

logger = get_logger(__name__)

_retriever_instance = None

CHUNK_TYPE_ORDER = ["transcript", "minutes", "action_item", "resolution"]

CHUNK_TYPE_LABEL = {
    "transcript": "转录",
    "minutes": "纪要",
    "action_item": "待办",
    "resolution": "决议",
}


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

    def rebuild_meeting_index(self, *args, **kwargs):
        pass

    def search(self, query, top_k=5, meeting_id=None, meeting_ids=None,
               exclude_meeting_id=None, chunk_type=None):
        return []

    def enrich_results(self, results):
        return []

    def remove_meeting(self, meeting_id):
        pass

    def build_context(self, query="", top_k=5, meeting_id=None, meeting_ids=None,
                      exclude_meeting_id=None, results=None):
        return ""


class Retriever:
    """基于 PGVector 的 RAG 检索器 — 覆盖式索引"""

    def __init__(self, embeddings):
        from rag.text_splitter import SimpleTextSplitter

        self.embeddings = embeddings
        self.engine = get_engine()
        self.splitter = SimpleTextSplitter(
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )

    # ── Public: 覆盖式索引重建 ──

    def rebuild_meeting_index(
        self, meeting_id, transcript="", minutes="", action_items="", resolutions=""
    ):
        """覆盖式重建会议索引：DELETE 旧 chunks → 生成新 chunks → 事务写入。

        相同 meeting_id 多次调用不会产生重复数据。
        """
        sources = [
            ("transcript", transcript),
            ("minutes", minutes),
            ("action_item", action_items),
            ("resolution", resolutions),
        ]

        structured_chunks = []
        for chunk_type, source_text in sources:
            if not source_text or not source_text.strip():
                continue
            raw_chunks = self.splitter.split_text(source_text)
            for i, chunk_text in enumerate(raw_chunks):
                structured_chunks.append({
                    "chunk_type": chunk_type,
                    "chunk_index": i,
                    "chunk_text": chunk_text,
                    "content_hash": self._hash_text(chunk_text),
                })

        if not structured_chunks:
            # 覆盖式语义：无有效文本时应清空旧索引
            with self.engine.begin() as conn:
                result = conn.execute(
                    text("DELETE FROM meeting_chunks WHERE meeting_id = :mid"),
                    {"mid": meeting_id},
                )
                if result.rowcount:
                    logger.info("会议 %s 无有效文本，已清空旧索引 (%s 个片段)", meeting_id, result.rowcount)
            return

        # 去重：同一类型内 content_hash 相同的合并
        seen = set()
        deduped = []
        for c in structured_chunks:
            key = (c["chunk_type"], c["content_hash"])
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        if len(deduped) < len(structured_chunks):
            logger.info("应用层去重: %d → %d chunks", len(structured_chunks), len(deduped))

        # 去重后按 chunk_type 重新编号，保证 chunk_index 连续
        type_counter = {}
        for c in deduped:
            ct = c["chunk_type"]
            idx = type_counter.get(ct, 0)
            c["chunk_index"] = idx
            type_counter[ct] = idx + 1

        # embedding 在事务外计算，避免长事务持有连接
        texts = [c["chunk_text"] for c in deduped]
        vectors = self.embeddings.embed_documents(texts)
        now = datetime.now()

        # 事务内：DELETE + INSERT
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM meeting_chunks WHERE meeting_id = :mid"),
                {"mid": meeting_id},
            )
            for chunk, vec in zip(deduped, vectors):
                conn.execute(
                    text(
                        "INSERT INTO meeting_chunks "
                        "(meeting_id, chunk_type, chunk_index, chunk_text, content_hash, embedding, created_at) "
                        "VALUES (:mid, :ctype, :cidx, :text, :hash, :vec, :ts)"
                    ),
                    {
                        "mid": meeting_id,
                        "ctype": chunk["chunk_type"],
                        "cidx": chunk["chunk_index"],
                        "text": chunk["chunk_text"],
                        "hash": chunk["content_hash"],
                        "vec": vec,
                        "ts": now,
                    },
                )

        type_counts = {}
        for c in deduped:
            type_counts[c["chunk_type"]] = type_counts.get(c["chunk_type"], 0) + 1
        logger.info(
            "会议 %s 索引重建完成，共 %s 个片段 (%s)",
            meeting_id, len(deduped),
            ", ".join(f"{t}={n}" for t, n in sorted(type_counts.items())),
        )

    def index_meeting(self, meeting_id, transcript="", minutes="", action_items="", resolutions=""):
        """[deprecated] 请使用 rebuild_meeting_index。保留以兼容旧调用。"""
        return self.rebuild_meeting_index(
            meeting_id,
            transcript=transcript,
            minutes=minutes,
            action_items=action_items,
            resolutions=resolutions,
        )

    # ── Public: 检索 ──

    def search(self, query, top_k=5, meeting_id=None, meeting_ids=None,
               exclude_meeting_id=None, chunk_type=None):
        """向量相似度检索，返回结构化 metadata

        会议范围控制（优先级递减）:
          meeting_ids    → IN 查询，多会议定向
          meeting_id     → 单会议定向
          都不传         → 全库检索
          exclude_meeting_id → 在上述范围中排除指定会议
        """
        from pgvector import Vector

        vec = Vector(self.embeddings.embed_query(query))

        conditions = []
        params = {"vec": vec, "k": top_k}

        if meeting_ids is not None:
            ids = tuple(meeting_ids)
            if len(ids) == 0:
                return []
            conditions.append("meeting_id = ANY(:meeting_ids)")
            params["meeting_ids"] = ids
        elif meeting_id is not None:
            conditions.append("meeting_id = :meeting_id")
            params["meeting_id"] = meeting_id

        if exclude_meeting_id is not None:
            conditions.append("meeting_id != :exclude_id")
            params["exclude_id"] = exclude_meeting_id
        if chunk_type is not None:
            conditions.append("chunk_type = :ctype")
            params["ctype"] = chunk_type

        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        sql = text(f"""
            SELECT meeting_id, chunk_type, chunk_index, chunk_text,
                   1 - (embedding <=> :vec) AS similarity
            FROM meeting_chunks
            WHERE {where_clause}
            ORDER BY embedding <=> :vec
            LIMIT :k
        """)

        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            {
                "meeting_id": row[0],
                "chunk_type": row[1],
                "chunk_index": row[2],
                "text": row[3],
                "score": round(row[4], 4),
            }
            for row in rows
        ]

    def remove_meeting(self, meeting_id):
        with self.engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM meeting_chunks WHERE meeting_id = :mid"),
                {"mid": meeting_id},
            )
            if result.rowcount:
                logger.info("已从知识库移除会议 %s 的 %s 个片段", meeting_id, result.rowcount)

    def enrich_results(self, results: list) -> list:
        """给 search() 结果补 meeting_title + chunk_type_label，供前端直接消费"""
        if not results:
            return []
        mids = sorted(set(r["meeting_id"] for r in results))
        title_map = self._get_meeting_titles(mids)
        enriched = []
        for r in results:
            r = dict(r)
            r["meeting_title"] = title_map.get(r["meeting_id"], f"会议#{r['meeting_id']}")
            r["chunk_type_label"] = CHUNK_TYPE_LABEL.get(r["chunk_type"], r["chunk_type"])
            enriched.append(r)
        return enriched

    def build_context(self, query="", top_k=5, meeting_id=None, meeting_ids=None,
                      exclude_meeting_id=None, results=None):
        """将检索结果拼成 LLM 可读文本。
        若传入 results 则跳过搜索（避免重复 embedding + 向量查询）；
        若 results 已 enriched（含 meeting_title），直接复用，不再查库。
        """
        if results is None:
            results = self.search(
                query, top_k=top_k,
                meeting_id=meeting_id, meeting_ids=meeting_ids,
                exclude_meeting_id=exclude_meeting_id,
            )
        if not results:
            return ""

        # 若结果已 enriched，直接复用标题；否则批量查一次
        if results and "meeting_title" in results[0]:
            title_map = {r["meeting_id"]: r["meeting_title"] for r in results}
        else:
            mids = sorted(set(r["meeting_id"] for r in results))
            title_map = self._get_meeting_titles(mids)

        lines = []
        for r in results:
            title = title_map.get(r["meeting_id"], f"会议#{r['meeting_id']}")
            label = CHUNK_TYPE_LABEL.get(r["chunk_type"], r["chunk_type"])
            lines.append(
                f"[《{title}》| {label} | 相似度 {r['score']:.2f}] {r['text']}"
            )
        return "\n\n".join(lines)

    # ── Private ──

    def _get_meeting_titles(self, meeting_ids: list) -> dict:
        """批量查询 meeting_id → title"""
        if not meeting_ids:
            return {}
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT id, title FROM meetings WHERE id = ANY(:ids)"
                    ),
                    {"ids": tuple(meeting_ids)},
                ).fetchall()
            return {row[0]: row[1] for row in rows}
        except Exception:
            return {}

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
