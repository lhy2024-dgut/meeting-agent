"""步骤 7：进阶实验 — ASR 误差 vs 干净转录对比实验

比较两种 RAG 知识库的检索效果：
  - ASR 转写（含语音识别错误）建库
  - 人工标注（干净）建库

用法：
    python evaluation/advanced_experiment.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import text
from db.engine import get_engine
from rag.retriever import get_retriever
from rag.embeddings import get_embeddings
from evaluation.qa_pairs import QA_PAIRS

logger = __import__("logging").getLogger(__name__)
ASR_PREFIX = "alimeeting_asr_near"
CLEAN_PREFIX = "alimeeting_near"


def build_asr_kb() -> list[str]:
    """用 ASR 转写结果（含错误）建知识库"""
    asr_data = json.loads(
        (BASE_DIR / "evaluation" / "asr_eval_results_near.json").read_text(encoding="utf-8")
    )

    groups = defaultdict(list)
    for item in asr_data["results"]:
        meeting_id = item["name"].rsplit("_SPK", 1)[0]
        groups[meeting_id].append(item["hypothesis"])

    meetings = {}
    for mid, texts in sorted(groups.items()):
        meetings[mid] = "\n".join(f"[说话人{i+1}] {t}" for i, t in enumerate(texts))

    retriever = get_retriever()
    created = []
    for meeting_id, transcript in meetings.items():
        kb_id = f"{ASR_PREFIX}_{meeting_id}"
        retriever.index_meeting(meeting_id=kb_id, transcript=transcript)
        created.append(kb_id)
        print(f"  ✅ ASR KB: {kb_id} ({len(transcript)} 字)")

    return created


def build_clean_kb() -> list[str]:
    """用干净人工标注建知识库"""
    data = json.loads(
        (BASE_DIR / "evaluation" / "alimeeting_near_parsed.json").read_text(encoding="utf-8")
    )
    groups = defaultdict(list)
    for item in data:
        meeting_id = item["file"].rsplit("_SPK", 1)[0]
        groups[meeting_id].append(item["full_text_clean"])

    meetings = {}
    for mid, texts in sorted(groups.items()):
        meetings[mid] = "\n".join(f"[说话人{i+1}] {t}" for i, t in enumerate(texts))

    retriever = get_retriever()
    created = []
    for meeting_id, transcript in meetings.items():
        kb_id = f"{CLEAN_PREFIX}_{meeting_id}"
        retriever.index_meeting(meeting_id=kb_id, transcript=transcript)
        created.append(kb_id)
        print(f"  ✅ 干净 KB: {kb_id} ({len(transcript)} 字)")

    return created


def remove_kb(prefix: str):
    """删除指定前缀的所有 KB 条目"""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text(f"DELETE FROM meeting_chunks WHERE meeting_id LIKE '{prefix}_%'")
        )
        conn.commit()
        print(f"  已删除 {prefix}_* 的旧数据")


def evaluate(prefix: str) -> dict:
    """对指定前缀的 KB 跑检索评估"""
    if not QA_PAIRS:
        return {"error": "No QA pairs"}

    # 用前缀过滤 meeting_id
    engine = get_engine()
    emb = get_embeddings()

    results = []
    recalls = []
    mrrs = []

    for i, qa in enumerate(QA_PAIRS, 1):
        vec = emb.embed_query(qa["q"])

        sql = text("""
            SELECT chunk_text, 1 - (embedding <=> CAST(:vec AS vector)) AS similarity
            FROM meeting_chunks
            WHERE meeting_id LIKE :prefix
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :k
        """)
        params = {"vec": vec, "prefix": f"{prefix}_%", "k": 5}

        with engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        retrieved = [{"score": round(row[1], 4), "text": row[0]} for row in rows]

        # 判断召回
        found = False
        first_rank = 0
        for rank, r in enumerate(retrieved, 1):
            if any(kw in r["text"] for kw in qa.get("keywords", [])):
                if not found:
                    found = True
                    first_rank = rank
                break

        if not found:
            for rank, r in enumerate(retrieved, 1):
                if qa["a"][:20] in r["text"]:
                    found = True
                    first_rank = rank
                    break

        recalls.append(1 if found else 0)
        mrrs.append(1.0 / first_rank if found else 0.0)

        status = "✅" if found else "❌"
        rank_str = f"rank {first_rank}" if found else "未命中"
        print(f"  [{i}/{len(QA_PAIRS)}] {status} {qa['meeting_id']} → {rank_str}")

    recall_at_5 = sum(recalls) / len(recalls) if recalls else 0
    mrr = sum(mrrs) / len(mrrs) if mrrs else 0

    print(f"\n  Recall@5: {recall_at_5:.2%} ({sum(recalls)}/{len(recalls)})")
    print(f"  MRR:      {mrr:.4f}")

    return {
        "num_qa": len(QA_PAIRS),
        "recall_at_5": round(recall_at_5, 4),
        "mrr": round(mrr, 4),
        "recall_pct": f"{recall_at_5:.2%}",
    }


def main():
    print("=" * 60)
    print("步骤 7：进阶实验 — ASR 误差 vs 干净转录")
    print("=" * 60)

    # 1. 先评估干净的（现有的）
    print("\n📊 Phase 1：干净人工标注转录")
    print("-" * 40)
    clean_result = evaluate(CLEAN_PREFIX)

    # 2. 建 ASR KB + 评估
    print(f"\n📊 Phase 2：用 ASR 转写（含错误）建 KB")
    print("-" * 40)
    remove_kb(ASR_PREFIX)
    build_asr_kb()
    print()
    asr_result = evaluate(ASR_PREFIX)

    # 3. 对比
    print("\n" + "=" * 60)
    print("📋 对比结果")
    print("=" * 60)
    print(f"  {'':20s}  {'Recall@5':>10s}  {'MRR':>8s}")
    print(f"  {'─' * 20}  {'─' * 10}  {'─' * 8}")

    cr = clean_result.get("recall_pct", "N/A")
    ar = asr_result.get("recall_pct", "N/A")
    cm = clean_result.get("mrr", 0)
    am = asr_result.get("mrr", 0)
    print(f"  {'干净转录':20s}  {cr:>10s}  {cm:>8.4f}")
    print(f"  {'ASR 转写':20s}  {ar:>10s}  {am:>8.4f}")

    if clean_result.get("recall_at_5") and asr_result.get("recall_at_5"):
        drop_recall = clean_result["recall_at_5"] - asr_result["recall_at_5"]
        drop_mrr = clean_result["mrr"] - asr_result["mrr"]
        print(f"  {'─' * 20}  {'─' * 10}  {'─' * 8}")
        print(f"  {'Recall 下降':20s}  {drop_recall:>9.2%}  {drop_mrr:>8.4f}")
        print(f"  {'MRR 下降':20s}  {'':>10s}  {drop_mrr:>8.4f}")

    # 4. 保存结果
    comparison = {
        "clean": clean_result,
        "asr": asr_result,
    }
    if clean_result.get("recall_at_5") and asr_result.get("recall_at_5"):
        comparison["recall_drop"] = round(
            clean_result["recall_at_5"] - asr_result["recall_at_5"], 4
        )
        comparison["mrr_drop"] = round(
            clean_result["mrr"] - asr_result["mrr"], 4
        )

    out_path = BASE_DIR / "evaluation" / "advanced_experiment_results.json"
    out_path.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n实验结果已保存到 {out_path}")
    print(f"实验代码: evaluation/advanced_experiment.py")
    print(f"QA 对:    evaluation/qa_pairs.py ({len(QA_PAIRS)} 个)")
    print(f"提示: 步骤6的 eval 用的是全部 KB（不区分前缀），")
    print(f"      步骤7精确按前缀过滤，结果更准确。")


if __name__ == "__main__":
    main()
