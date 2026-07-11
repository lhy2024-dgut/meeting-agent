"""BM25 索引 — 基于 jieba 分词 + rank_bm25 的应用层全文检索"""

import jieba

from logger import get_logger

logger = get_logger(__name__)

_bm25_instance = None


def get_bm25_index():
    """返回全局 BM25Index 单例"""
    global _bm25_instance
    if _bm25_instance is None:
        _bm25_instance = BM25Index()
    return _bm25_instance


class BM25Index:
    """应用层 BM25 索引，内存中维护。

    每个 chunk 作为一个文档，jieba 分词后构建倒排索引。
    支持按 meeting_id 增量更新，无需全量重建。
    """

    def __init__(self):
        # chunk_id → {"meeting_id", "chunk_type", "chunk_index", "text", "tokens"}
        self._docs: dict[int, dict] = {}
        # 当前 BM25 实例（脏标记法，add/remove 后置 None 重建）
        self._bm25 = None  # rank_bm25 懒加载，避免未安装时整模块报错
        self._doc_ids: list[int] = []  # 与 BM25 语料库对齐的 id 列表

    def add_documents(self, meeting_id: int, chunks: list[dict]):
        """添加一批 chunks 到索引。

        chunks 格式: [{"id": int, "chunk_type": str, "chunk_index": int, "text": str}, ...]
        调用前会自动清除该 meeting_id 的旧数据（覆盖语义）。
        """
        self.remove_meeting(meeting_id)
        for c in chunks:
            tokens = self._tokenize(c["text"])
            self._docs[c["id"]] = {
                "meeting_id": meeting_id,
                "chunk_type": c["chunk_type"],
                "chunk_index": c["chunk_index"],
                "text": c["text"],
                "tokens": tokens,
            }
        self._bm25 = None  # 标记需要重建
        logger.info("BM25 索引: 添加会议 %s 的 %d 个 chunk", meeting_id, len(chunks))

    def remove_meeting(self, meeting_id: int):
        """移除指定会议的所有文档"""
        to_remove = [cid for cid, d in self._docs.items() if d["meeting_id"] == meeting_id]
        for cid in to_remove:
            del self._docs[cid]
        if to_remove:
            self._bm25 = None
            logger.info("BM25 索引: 移除会议 %s 的 %d 个 chunk", meeting_id, len(to_remove))

    def search(self, query: str, top_k: int = 5,
               meeting_id=None, meeting_ids=None,
               exclude_meeting_id=None, chunk_type=None) -> list[dict]:
        """BM25 检索，支持按 meeting_id/chunk_type 限定子语料后再取 top_k。

        先过滤文档集合，再在子集上计算 BM25 分数，避免"全库 top-k 再过滤"
        导致范围内有效结果被遗漏的问题。

        返回格式与 Retriever.search() 一致:
        [{"meeting_id", "chunk_type", "chunk_index", "text", "score"}, ...]
        """
        if not self._docs:
            return []

        # 构建过滤后的文档子集
        filtered_ids = self._filter_docs(meeting_id, meeting_ids,
                                         exclude_meeting_id, chunk_type)
        if not filtered_ids:
            return []

        # 在子集上计算 BM25 分数
        query_tokens = self._tokenize(query)

        if self._uses_full_corpus(meeting_id, meeting_ids, exclude_meeting_id, chunk_type):
            bm25, filtered_ids = self._get_bm25()
            scores = bm25.get_scores(query_tokens)
        else:
            # 构建子语料 BM25（仅含过滤后的文档）
            from rank_bm25 import BM25Okapi
            sub_corpus = [self._docs[cid]["tokens"] for cid in filtered_ids]
            sub_bm25 = BM25Okapi(sub_corpus)
            scores = sub_bm25.get_scores(query_tokens)

        if len(scores) == 0:
            return []

        import numpy as np
        # 取 top_k（候选集已过滤，直接取即可）
        actual_k = min(top_k, len(scores))
        top_indices = np.argsort(scores)[::-1][:actual_k]

        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score <= 0:
                continue
            doc_id = filtered_ids[idx]
            doc = self._docs[doc_id]
            results.append({
                "meeting_id": doc["meeting_id"],
                "chunk_type": doc["chunk_type"],
                "chunk_index": doc["chunk_index"],
                "text": doc["text"],
                "score": round(score, 4),
            })
        return results

    def _filter_docs(self, meeting_id=None, meeting_ids=None,
                     exclude_meeting_id=None, chunk_type=None) -> list[int]:
        """按条件过滤文档 ID 列表"""
        ids = list(self._docs.keys())

        if meeting_ids is not None:
            ids = [cid for cid in ids if self._docs[cid]["meeting_id"] in meeting_ids]
        elif meeting_id is not None:
            ids = [cid for cid in ids if self._docs[cid]["meeting_id"] == meeting_id]

        if exclude_meeting_id is not None:
            ids = [cid for cid in ids if self._docs[cid]["meeting_id"] != exclude_meeting_id]

        if chunk_type is not None:
            ids = [cid for cid in ids if self._docs[cid]["chunk_type"] == chunk_type]

        return ids

    @staticmethod
    def _uses_full_corpus(meeting_id=None, meeting_ids=None,
                          exclude_meeting_id=None, chunk_type=None) -> bool:
        return (
            meeting_id is None
            and meeting_ids is None
            and exclude_meeting_id is None
            and chunk_type is None
        )

    def clear(self):
        """清空全部索引"""
        self._docs.clear()
        self._bm25 = None
        self._doc_ids = []

    @property
    def doc_count(self) -> int:
        return len(self._docs)

    def _get_bm25(self):
        """懒加载 BM25 实例，索引变更后自动重建"""
        if self._bm25 is None:
            from rank_bm25 import BM25Okapi
            self._doc_ids = list(self._docs.keys())
            corpus = [self._docs[cid]["tokens"] for cid in self._doc_ids]
            self._bm25 = BM25Okapi(corpus)
        return self._bm25, self._doc_ids

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """jieba 分词，过滤空白 token"""
        return [w for w in jieba.lcut(text) if w.strip()]
