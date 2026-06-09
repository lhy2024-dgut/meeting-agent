"""步骤 5：构建 RAG 知识库 — 把 AliMeeting 人工标注转录存进向量库

用法：
    python evaluation/build_kb.py                   # 索引全部
    python evaluation/build_kb.py --source near      # 只索引近场
    python evaluation/build_kb.py --dry-run          # 只看不存
"""

import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from rag.retriever import get_retriever


def index_meetings(meetings: dict, source_name: str, dry_run: bool = False) -> list[dict]:
    """把会议转录索引到知识库"""
    retriever = get_retriever()
    if isinstance(retriever.__class__.__name__, str) and "Dummy" in type(retriever).__name__:
        print("  ⚠️  Retriever 是 DummyRetriever（向量库未连接），索引失败")
        return []

    results = []
    for i, (meeting_id, transcript) in enumerate(meetings.items(), 1):
        # 用阿里会议 ID + 前缀确保唯一
        kb_id = f"alimeeting_{source_name}_{meeting_id}"
        print(f"[{i}/{len(meetings)}] {kb_id}")
        print(f"    转录长度: {len(transcript)} 字")

        if dry_run:
            print(f"    [DRY RUN] 跳过索引")
            results.append({
                "meeting_id": kb_id,
                "transcript_len": len(transcript),
                "status": "skipped (dry-run)",
            })
            continue

        t0 = time.time()
        try:
            retriever.index_meeting(
                meeting_id=kb_id,
                transcript=transcript,
                minutes="",
                action_items="",
                resolutions="",
            )
            elapsed = time.time() - t0
            print(f"    索引完成 ({elapsed:.1f}s)")
            results.append({
                "meeting_id": kb_id,
                "transcript_len": len(transcript),
                "status": "indexed",
                "elapsed_sec": round(elapsed, 1),
            })
        except Exception as e:
            elapsed = time.time() - t0
            print(f"    索引失败 ({elapsed:.1f}s): {e}")
            results.append({
                "meeting_id": kb_id,
                "transcript_len": len(transcript),
                "status": f"failed: {e}",
                "elapsed_sec": round(elapsed, 1),
            })
        print()

    return results


def main():
    import argparse
    from collections import defaultdict

    parser = argparse.ArgumentParser(description="构建 RAG 知识库")
    parser.add_argument("--source", choices=["near", "far", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true", help="只看不存")
    args = parser.parse_args()

    # 加载数据
    all_data = {}

    if args.source in ("near", "all"):
        data = json.loads(
            (BASE_DIR / "evaluation" / "alimeeting_near_parsed.json").read_text(encoding="utf-8")
        )
        groups = defaultdict(list)
        for item in data:
            meeting_id = item["file"].rsplit("_SPK", 1)[0]
            groups[meeting_id].append(item["full_text_clean"])
        near_meetings = {
            mid: "\n".join(f"[说话人{i+1}] {t}" for i, t in enumerate(texts))
            for mid, texts in groups.items()
        }
        all_data["near"] = near_meetings

    if args.source in ("far", "all"):
        data = json.loads(
            (BASE_DIR / "evaluation" / "alimeeting_far_parsed.json").read_text(encoding="utf-8")
        )
        far_meetings = {
            item["file"].replace(".TextGrid", ""): item["full_text_clean"]
            for item in data
        }
        all_data["far"] = far_meetings

    # 逐个源索引
    all_results = {}
    for source_name, meetings in all_data.items():
        print(f"\n{'=' * 60}")
        print(f"索引 {source_name} 数据（{len(meetings)} 场会议）")
        print(f"{'=' * 60}\n")
        results = index_meetings(meetings, source_name, args.dry_run)
        all_results[source_name] = results

    # 保存索引记录
    out_path = BASE_DIR / "evaluation" / "kb_index_log.json"
    out_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n索引记录已保存到 {out_path}")

    # 汇总
    total = sum(len(v) for v in all_results.values())
    indexed = sum(
        1 for results in all_results.values() for r in results
        if r.get("status") == "indexed"
    )
    print(f"\n总计: {indexed}/{total} 场会议索引成功")


if __name__ == "__main__":
    main()
