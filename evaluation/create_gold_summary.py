"""步骤 4：生成金标准摘要 — 用 LLM 基于人工标注转录生成会议纪要

用法：
    python evaluation/create_gold_summary.py              # 跑全部 8 场会议
    python evaluation/create_gold_summary.py --limit 2     # 只跑前 2 场（试试水）
"""

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from chains.minutes_chain import MinutesChain


def load_near_transcripts() -> dict:
    """加载近场 parsed JSON，按会议分组返回 {meeting_id: 合并后的转录}"""
    data = json.loads(
        (BASE_DIR / "evaluation" / "alimeeting_near_parsed.json").read_text(encoding="utf-8")
    )

    groups = defaultdict(list)
    for item in data:
        # "R8001_M8004_N_SPK8013.TextGrid" → "R8001_M8004"
        meeting_id = item["file"].rsplit("_SPK", 1)[0]
        groups[meeting_id].append(item["full_text_clean"])

    result = {}
    for mid, texts in sorted(groups.items()):
        # 按说话人顺序拼接
        result[mid] = "\n".join(f"[说话人{i+1}] {t}" for i, t in enumerate(texts))
    return result


def load_far_transcripts() -> dict:
    """加载远场 parsed JSON（本来就是完整的多人会议转录）"""
    data = json.loads(
        (BASE_DIR / "evaluation" / "alimeeting_far_parsed.json").read_text(encoding="utf-8")
    )
    return {item["file"].replace(".TextGrid", ""): item["full_text_clean"] for item in data}


def generate_summaries(meetings: dict, limit: int | None = None) -> list[dict]:
    """对每场会议生成金标准摘要"""
    chain = MinutesChain()
    results = []

    items = list(meetings.items())
    if limit:
        items = items[:limit]

    for i, (meeting_id, transcript) in enumerate(items, 1):
        print(f"[{i}/{len(items)}] {meeting_id}")
        print(f"    转录长度: {len(transcript)} 字")

        t0 = time.time()
        try:
            action_items, resolutions, minutes = chain.run(transcript, title=meeting_id)
            elapsed = time.time() - t0
            print(f"    生成完成 ({elapsed:.1f}s)")

            results.append({
                "meeting_id": meeting_id,
                "transcript_len": len(transcript),
                "action_items": action_items,
                "resolutions": resolutions,
                "minutes": minutes,
                "elapsed_sec": round(elapsed, 1),
            })
        except Exception as e:
            elapsed = time.time() - t0
            print(f"    生成失败 ({elapsed:.1f}s): {e}")
            results.append({
                "meeting_id": meeting_id,
                "transcript_len": len(transcript),
                "action_items": "",
                "resolutions": "",
                "minutes": f"[生成失败] {e}",
                "elapsed_sec": round(elapsed, 1),
            })
        print()

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="生成金标准摘要")
    parser.add_argument("--limit", type=int, help="跑前 N 场会议")
    parser.add_argument("--source", choices=["near", "far", "all"], default="all",
                        help="数据源：near(近场), far(远场), all(都跑)")
    args = parser.parse_args()

    all_results = {}

    if args.source in ("near", "all"):
        print("=" * 60)
        print("近场数据 — 按会议分组生成摘要")
        print("=" * 60)
        meetings = load_near_transcripts()
        print(f"共 {len(meetings)} 场会议\n")
        near_results = generate_summaries(meetings, args.limit)
        all_results["near"] = near_results

    if args.source in ("far", "all"):
        print("\n" + "=" * 60)
        print("远场数据 — 生成摘要")
        print("=" * 60)
        meetings = load_far_transcripts()
        print(f"共 {len(meetings)} 场会议\n")
        far_results = generate_summaries(meetings, args.limit)
        all_results["far"] = far_results

    # 保存结果
    out_path = BASE_DIR / "evaluation" / "gold_summaries.json"
    out_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n摘要已保存到 {out_path}")


if __name__ == "__main__":
    main()
