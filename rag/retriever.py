"""RAG 检索器 — PGVector + BM25 + Reranker + 覆盖式索引 + 依赖注入"""

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

# RRF 融合常数
RRF_K = 60


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
               exclude_meeting_id=None, chunk_type=None, mode=None,
               enable_reranker=None):
        return []

    def enrich_results(self, results):
        return []

    def remove_meeting(self, meeting_id):
        pass

    def build_context(self, query="", top_k=5, meeting_id=None, meeting_ids=None,
                      exclude_meeting_id=None, results=None):
        return ""


class Retriever:
    """基于 PGVector + BM25 + Reranker 的 RAG 检索器 — 覆盖式索引

    支持三种检索模式（通过 search(mode=...) 切换）：
      - "vector"  : 纯向量检索（默认，向后兼容）
      - "bm25"    : 纯 BM25 关键词检索
      - "hybrid"  : BM25 + 向量 RRF 融合
    Reranker 在所有模式下均可选，通过 enable_reranker=True 开启。
    """

    def __init__(self, embeddings):
        from rag.text_splitter import SimpleTextSplitter

        self.embeddings = embeddings
        self.engine = get_engine()
        self.splitter = SimpleTextSplitter(
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )

        # BM25 索引（懒加载）
        self._bm25_index = None

        # Reranker（懒加载）
        self._reranker = None
        self._reranker_loaded = False

    @property
    def bm25_index(self):
        """懒加载 BM25 索引"""
        if self._bm25_index is None:
            from rag.bm25_index import BM25Index
            self._bm25_index = BM25Index()
            self._load_bm25_from_db()
        return self._bm25_index

    def _get_reranker(self):
        """懒加载 Reranker，状态明确打印"""
        if not self._reranker_loaded:
            self._reranker_loaded = True
            if getattr(config, "RERANKER_ENABLED", True):
                try:
                    from rag.reranker import DummyReranker, get_reranker
                    reranker = get_reranker()
                    if isinstance(reranker, DummyReranker):
                        logger.warning("[Reranker] 降级模式 — 检索结果未经精排")
                    self._reranker = reranker
                except Exception as e:
                    logger.warning("[Reranker] 加载异常，跳过重排序: %s", e)
                    self._reranker = None
            else:
                logger.info("[Reranker] 已禁用 (RERANKER_ENABLED=false)")
        return self._reranker

    def _load_bm25_from_db(self):
        """从数据库加载已有 chunks 到 BM25 索引"""
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT id, meeting_id, chunk_type, chunk_index, chunk_text FROM meeting_chunks")
                ).fetchall()
            if rows:
                chunks = [
                    {"id": r[0], "meeting_id": r[1], "chunk_type": r[2],
                     "chunk_index": r[3], "text": r[4]}
                    for r in rows
                ]
                # 按 meeting_id 分组添加
                from collections import defaultdict
                by_meeting = defaultdict(list)
                for c in chunks:
                    by_meeting[c["meeting_id"]].append(c)
                for mid, mchunks in by_meeting.items():
                    self._bm25_index.add_documents(mid, mchunks)
                logger.info("BM25 索引从数据库加载完成，共 %d 个 chunk", len(chunks))
        except Exception as e:
            logger.warning("从数据库加载 BM25 索引失败: %s", e)

    # ── Public: 覆盖式索引重建 ──

    def rebuild_meeting_index(
        self, meeting_id, transcript="", minutes="", action_items="", resolutions=""
    ):
        """覆盖式重建会议索引：DELETE 旧 chunks → 生成新 chunks → 事务写入。

        相同 meeting_id 多次调用不会产生重复数据。
        同时更新向量索引和 BM25 索引。
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
            # 同步更新 BM25
            if self._bm25_index is not None:
                self._bm25_index.remove_meeting(meeting_id)
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

        # 同步更新 BM25 索引：重新从 DB 加载该会议的 chunk（含自增 id）
        if self._bm25_index is not None:
            try:
                with self.engine.connect() as conn:
                    rows = conn.execute(
                        text(
                            "SELECT id, chunk_type, chunk_index, chunk_text "
                            "FROM meeting_chunks WHERE meeting_id = :mid"
                        ),
                        {"mid": meeting_id},
                    ).fetchall()
                bm25_chunks = [
                    {"id": r[0], "chunk_type": r[1], "chunk_index": r[2], "text": r[3]}
                    for r in rows
                ]
                self._bm25_index.add_documents(meeting_id, bm25_chunks)
            except Exception as e:
                logger.warning("同步 BM25 索引失败: %s", e)

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
               exclude_meeting_id=None, chunk_type=None, mode=None,
               enable_reranker=None):
        """统一检索入口，支持 vector / bm25 / hybrid 三种模式。

        Args:
            query: 用户查询
            top_k: 返回结果数
            meeting_id/meeting_ids/exclude_meeting_id/chunk_type: 过滤条件
            mode: "vector" | "bm25" | "hybrid"，默认读 config.SEARCH_MODE
            enable_reranker: 是否启用 Reranker，默认读 config.RERANKER_ENABLED

        Returns:
            结构化结果列表，格式与原 search() 一致
        """
        # [P1] 短路：meeting_ids=[] 表示"不查任何会议"，直接返回空
        if meeting_ids is not None and len(meeting_ids) == 0:
            return []

        if mode is None:
            mode = getattr(config, "SEARCH_MODE", "vector")

        # 构建过滤条件（供 SQL 查询使用）
        conditions, params, bm25_filters = self._build_filters(
            meeting_id=meeting_id, meeting_ids=meeting_ids,
            exclude_meeting_id=exclude_meeting_id, chunk_type=chunk_type,
        )

        # 按模式分发
        if mode == "bm25":
            results = self._bm25_search(
                query, top_k=top_k, bm25_filters=bm25_filters,
            )
        elif mode == "hybrid":
            results = self._hybrid_search(
                query, top_k=top_k, conditions=conditions, params=params, bm25_filters=bm25_filters,
            )
        else:
            results = self._vector_search(
                query, top_k=top_k, conditions=conditions, params=params,
            )

        # [P2] 分数阈值：过滤弱相关结果，避免低质量内容污染 LLM 上下文
        min_score = getattr(config, "MIN_SCORE_THRESHOLD", 0.0)
        if min_score > 0 and results:
            results = [r for r in results if r.get("score", 0) >= min_score]

        # 可选：Reranker 二次排序
        if enable_reranker is None:
            enable_reranker = getattr(config, "RERANKER_ENABLED", True)
        if enable_reranker and results:
            reranker = self._get_reranker()
            if reranker and not isinstance(reranker, type(None)):
                results = reranker.rerank(query, results, top_k=top_k)
                # Reranker 后也应用阈值（rerank_score 与原始 score 量纲不同）
                min_rerank = getattr(config, "MIN_RERANK_SCORE", 0.0)
                if min_rerank > 0:
                    results = [r for r in results if r.get("rerank_score", 0) >= min_rerank]

        return results

    def _build_filters(self, meeting_id=None, meeting_ids=None,
                       exclude_meeting_id=None, chunk_type=None):
        """构建 SQL WHERE 条件和参数。

        注意：meeting_ids=[] 已在 search() 开头短路，这里不会收到空列表。
        """
        conditions = []
        params = {}
        bm25_filters = {}

        if meeting_ids is not None:
            ids = tuple(meeting_ids)
            conditions.append("meeting_id = ANY(:meeting_ids)")
            params["meeting_ids"] = ids
            bm25_filters["meeting_ids"] = list(meeting_ids)
        elif meeting_id is not None:
            conditions.append("meeting_id = :meeting_id")
            params["meeting_id"] = meeting_id
            bm25_filters["meeting_id"] = meeting_id

        if exclude_meeting_id is not None:
            conditions.append("meeting_id != :exclude_id")
            params["exclude_id"] = exclude_meeting_id
            bm25_filters["exclude_meeting_id"] = exclude_meeting_id
        if chunk_type is not None:
            conditions.append("chunk_type = :ctype")
            params["ctype"] = chunk_type

            bm25_filters["chunk_type"] = chunk_type

        return conditions, params, bm25_filters

    def _vector_search(self, query, top_k=5, conditions=None, params=None):
        """纯向量相似度检索"""
        from pgvector import Vector

        if params is None:
            params = {}

        vec = Vector(self.embeddings.embed_query(query))
        params["vec"] = vec
        params["k"] = top_k

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

    def _bm25_search(self, query, top_k=5, bm25_filters=None):
        """纯 BM25 关键词检索，支持按 meeting_id/chunk_type 限定子语料"""
        return self.bm25_index.search(query, top_k=top_k, **(bm25_filters or {}))

    def _hybrid_search(self, query, top_k=5, conditions=None, params=None, bm25_filters=None):
        """BM25 + 向量检索 RRF 融合

        RRF 公式: score(d) = Σ 1/(k + rank_i(d))，k=60
        两路各召回 top_k*recall_multiplier 条，融合后取 top_k 条。
        两路都直接按过滤条件限定子语料，不做后置过滤。
        """
        recall_multiplier = getattr(config, "RECALL_MULTIPLIER", 4)
        recall_k = top_k * recall_multiplier

        # 路径 A: 向量检索（SQL 级过滤）
        vector_results = self._vector_search(
            query, top_k=recall_k, conditions=conditions, params=params,
        )

        # 路径 B: BM25 检索（子语料级过滤）
        bm25_results = self._bm25_search(
            query, top_k=recall_k, bm25_filters=bm25_filters,
        )

        # RRF 融合
        rrf_scores = {}
        result_map = {}

        for rank, r in enumerate(vector_results):
            key = (r["meeting_id"], r["chunk_type"], r["chunk_index"])
            rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (RRF_K + rank + 1)
            result_map[key] = r

        for rank, r in enumerate(bm25_results):
            key = (r["meeting_id"], r["chunk_type"], r["chunk_index"])
            rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (RRF_K + rank + 1)
            if key not in result_map:
                result_map[key] = r

        # 按 RRF 分数排序
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)

        results = []
        for key in sorted_keys[:top_k]:
            r = dict(result_map[key])
            r["score"] = round(rrf_scores[key], 4)
            results.append(r)

        return results

    def remove_meeting(self, meeting_id):
        with self.engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM meeting_chunks WHERE meeting_id = :mid"),
                {"mid": meeting_id},
            )
            if result.rowcount:
                logger.info("已从知识库移除会议 %s 的 %s 个片段", meeting_id, result.rowcount)
        # 同步 BM25
        if self._bm25_index is not None:
            self._bm25_index.remove_meeting(meeting_id)

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
        若结果已 enriched（含 meeting_title），直接复用，不再查库。
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
