"""Reranker — 基于 transformers CrossEncoder 的二次排序"""

from logger import get_logger

logger = get_logger(__name__)

_reranker_instance = None


def get_reranker(model_name: str = None):
    """返回全局 Reranker 单例，启动时打印明确健康状态"""
    global _reranker_instance
    if _reranker_instance is None:
        import config
        model = model_name or getattr(config, "RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
        try:
            _reranker_instance = Reranker(model)
            logger.info("[Reranker] 已启用: %s", model)
        except Exception as e:
            logger.warning("[Reranker] 加载失败，已降级为 DummyReranker（不影响基础检索）: %s", e)
            _reranker_instance = DummyReranker()
    return _reranker_instance


class DummyReranker:
    """Reranker 不可用时的降级实现，直接透传原结果"""

    def rerank(self, query: str, results: list, top_k: int = 5) -> list:
        return results[:top_k]


class Reranker:
    """基于 transformers 的 CrossEncoder Reranker。

    直接用 AutoTokenizer + AutoModelForSequenceClassification，
    绕过 FlagEmbedding 的兼容性问题。
    CPU 可跑，~200ms/query。
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        import torch

        logger.info("正在加载 Reranker 模型: %s ...", model_name)

        # 如果是本地路径且存在，直接加载；否则从 HuggingFace 下载
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.eval()

        self._torch = torch
        self.model_name = model_name
        logger.info("Reranker 模型加载完成")

    def rerank(self, query: str, results: list, top_k: int = 5) -> list:
        """对检索结果进行二次排序。

        Args:
            query: 用户查询
            results: 原始检索结果，每项需包含 "text" 字段
            top_k: 返回前 top_k 条

        Returns:
            重排序后的 top_k 条结果，增加 "rerank_score" 字段
        """
        if not results:
            return []

        # 构造 (query, doc) 对
        pairs = [[query, r["text"]] for r in results]

        # tokenize
        inputs = self.tokenizer(
            pairs,
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=512,
        )

        # 推理
        with self._torch.no_grad():
            scores = self.model(**inputs).logits.squeeze(-1)

        # 单条结果时 scores 是标量
        if scores.dim() == 0:
            scores = scores.unsqueeze(0)

        scores_list = scores.tolist()
        if isinstance(scores_list, (int, float)):
            scores_list = [scores_list]

        reranked = []
        for result, score in zip(results, scores_list):
            item = dict(result)
            item["rerank_score"] = round(float(score), 4)
            reranked.append(item)

        reranked.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return reranked[:top_k]
