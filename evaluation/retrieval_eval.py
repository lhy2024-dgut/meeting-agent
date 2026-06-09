"""步骤 6：检索评估 — 算 Recall@5 和 MRR

用法：
    python evaluation/retrieval_eval.py                      # 用标注的 QA 对评估
    python evaluation/retrieval_eval.py --kb-prefix near     # 只评估近场 KB
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from rag.retriever import get_retriever
from evaluation.qa_pairs import QA_PAIRS


def evaluate_retrieval(qa_pairs: list[dict], kb_prefix: str = "alimeeting_near") -> dict:
    """对 QA 对跑检索评估，算 Recall@5 和 MRR"""
    retriever = get_retriever()
    if isinstance(type(retriever).__name__, str) and "Dummy" in type(retriever).__name__:
        return {"error": "Retriever is DummyRetriever, cannot evaluate"}

    if not qa_pairs:
        return {"error": "No QA pairs"}

    results = []
    recalls = []
    mrrs = []

    for i, qa in enumerate(qa_pairs, 1):
        meeting_id = qa["meeting_id"]
        kb_meeting_id = f"{kb_prefix}_{meeting_id}"

        # 搜索
        try:
            retrieved = retriever.search(qa["q"], top_k=5, exclude_meeting_id=None)
        except Exception as e:
            print(f"[{i}] {qa['q'][:40]}... 搜索失败: {e}")
            continue

        # 判断召回：片段文本是否包含答案中的关键词
        found = False
        first_rank = 0
        for rank, r in enumerate(retrieved, 1):
            text = r.get("text", "")
            # 检查是否命中任何关键词
            if any(kw in text for kw in qa.get("keywords", [])):
                if not found:
                    found = True
                    first_rank = rank
                break  # 只取第一个命中

        # 或者检查答案文本是否在片段中
        if not found:
            for rank, r in enumerate(retrieved, 1):
                if qa["a"][:20] in r.get("text", ""):
                    found = True
                    first_rank = rank
                    break

        recalls.append(1 if found else 0)
        mrrs.append(1.0 / first_rank if found else 0.0)

        print(f"[{i}/{len(qa_pairs)}] {qa['meeting_id']}")
        print(f"    Q: {qa['q'][:50]}")
        print(f"    {'✅ 命中' if found else '❌ 未命中'} "
              f"({'排名 ' + str(first_rank) if found else ''})")

        # 显示前 3 个召回结果
        for j, r in enumerate(retrieved[:3], 1):
            score = r.get("score", 0)
            text_preview = r.get("text", "")[:60]
            print(f"       #{j} (相似度 {score:.3f}) {text_preview}...")
        print()

    # 汇总
    recall_at_5 = sum(recalls) / len(recalls) if recalls else 0
    mrr = sum(mrrs) / len(mrrs) if mrrs else 0

    print("=" * 60)
    print("检索评估结果")
    print("=" * 60)
    print(f"  QA 对总数: {len(qa_pairs)}")
    print(f"  Recall@5:  {recall_at_5:.2%}  ({sum(recalls)}/{len(recalls)})")
    print(f"  MRR:       {mrr:.4f}")
    print(f"  排序详情:  {[round(m, 3) for m in mrrs]}")

    return {
        "kb_prefix": kb_prefix,
        "num_qa": len(qa_pairs),
        "recall_at_5": round(recall_at_5, 4),
        "mrr": round(mrr, 4),
        "recall_pct": f"{recall_at_5:.2%}",
        "individual_results": [
            {"q": qa["q"], "recalled": r, "mrr": m}
            for qa, r, m in zip(qa_pairs, recalls, mrrs)
        ],
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="RAG 检索评估")
    parser.add_argument("--kb-prefix", default="alimeeting_near",
                        help="知识库会议 ID 前缀（默认 alimeeting_near）")
    args = parser.parse_args()

    result = evaluate_retrieval(QA_PAIRS, kb_prefix=args.kb_prefix)

    # 保存结果
    out_path = BASE_DIR / "evaluation" / "retrieval_eval_results.json"
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n评估结果已保存到 {out_path}")


if __name__ == "__main__":
    main()
