"""步骤：ASR 转录 → 会议纪要生成 → 对比金标准

用 ASR 转写结果（hypothesis）通过 MinutesChain 生成会议纪要，
跟金标准（基于人工标注转录生成的纪要）做对比。

用法：
    python evaluation/asr_minutes_eval.py                 # 跑全部 8 场近场会议
    python evaluation/asr_minutes_eval.py --limit 2       # 只跑前 2 场
"""

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from chains.minutes_chain import MinutesChain


def load_asr_transcripts() -> dict:
    """从 ASR 评估结果加载 hypothesis，按会议分组"""
    data = json.loads(
        (BASE_DIR / "evaluation" / "asr_eval_results_near.json").read_text(encoding="utf-8")
    )

    groups = defaultdict(list)
    for item in data["results"]:
        # "R8001_M8004_N_SPK8013" → "R8001_M8004"
        meeting_id = item["name"].rsplit("_SPK", 1)[0]
        groups[meeting_id].append(item["hypothesis"])

    result = {}
    for mid, texts in sorted(groups.items()):
        # 按说话人顺序拼接（和 create_gold_summary.py 一致）
        result[mid] = "\n".join(f"[说话人{i+1}] {t}" for i, t in enumerate(texts))
    return result


def load_gold_summaries() -> dict:
    """加载金标准摘要"""
    data = json.loads(
        (BASE_DIR / "evaluation" / "gold_summaries.json").read_text(encoding="utf-8")
    )
    gold = {}
    for item in data.get("near", []):
        gold[item["meeting_id"]] = {
            "minutes": item["minutes"],
            "action_items": item["action_items"],
            "resolutions": item["resolutions"],
            "transcript_len": item["transcript_len"],
        }
    return gold


def generate_asr_minutes(meetings: dict, limit: int | None = None) -> list[dict]:
    """对每场会议的 ASR 转录生成会议纪要"""
    chain = MinutesChain()
    results = []

    items = list(meetings.items())
    if limit:
        items = items[:limit]

    for i, (meeting_id, transcript) in enumerate(items, 1):
        print(f"[{i}/{len(items)}] {meeting_id}")
        print(f"    ASR 转录长度: {len(transcript)} 字")

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


def compare_minutes(asr_results: list[dict], gold: dict) -> list[dict]:
    """对比 ASR 纪要和金标准，输出对照结果"""
    comparison = []
    for item in asr_results:
        mid = item["meeting_id"]
        g = gold.get(mid, {})

        entry = {
            "meeting_id": mid,
            "asr_transcript_len": item["transcript_len"],
            "gold_transcript_len": g.get("transcript_len", 0),
            "length_ratio": round(item["transcript_len"] / max(g.get("transcript_len", 1), 1), 2),
            "asr_elapsed_sec": item["elapsed_sec"],
            "asr_minutes_len": len(item["minutes"]),
            "gold_minutes_len": len(g.get("minutes", "")),
            "minutes_len_ratio": round(len(item["minutes"]) / max(len(g.get("minutes", "")), 1), 2),
            "status": "OK" if item["action_items"] != "" else "FAIL",
        }
        comparison.append(entry)
    return comparison


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ASR → 纪要对比评估")
    parser.add_argument("--limit", type=int, help="跑前 N 场会议")
    parser.add_argument("--review", action="store_true",
                        help="同时生成 review.md 对照文件进行人工审阅")
    args = parser.parse_args()

    # 1. 加载 ASR 转录
    print("=" * 60)
    print("加载 ASR 转录结果（按会议分组）")
    print("=" * 60)
    asr_meetings = load_asr_transcripts()
    print(f"共 {len(asr_meetings)} 场会议\n")

    # 2. 加载金标准
    print("加载金标准摘要...")
    gold = load_gold_summaries()
    print(f"共 {len(gold)} 场金标准\n")

    # 3. 用 ASR 转录生成会议纪要
    print("=" * 60)
    print("用 ASR 转录生成会议纪要")
    print("=" * 60)
    asr_results = generate_asr_minutes(asr_meetings, args.limit)

    # 4. 对比
    print("=" * 60)
    print("对比结果")
    print("=" * 60)
    comparison = compare_minutes(asr_results, gold)

    print(f"\n{'会议ID':<20} {'ASR字数':<10} {'金标准字数':<12} {'长度比':<8} {'ASR纪要字数':<12} {'金标准纪要字数':<14} {'状态':<6}")
    print("-" * 80)
    for c in comparison:
        print(f"{c['meeting_id']:<20} {c['asr_transcript_len']:<10} {c['gold_transcript_len']:<12} {c['length_ratio']:<8} {c['asr_minutes_len']:<12} {c['gold_minutes_len']:<14} {c['status']:<6}")
    print()

    # 5. 保存结果
    output = {
        "dataset": "AliMeeting Eval Near",
        "asr_model": "Faster-Whisper base",
        "llm": "qwen3.5:4b",
        "num_meetings": len(asr_results),
        "comparison": comparison,
        "asr_minutes": asr_results,
    }
    out_path = BASE_DIR / "evaluation" / "asr_minutes_results.json"
    out_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"结果已保存到 {out_path}")

    # 6. 可选：生成人工校对稿
    if args.review:
        review_path = BASE_DIR / "evaluation" / "asr_minutes_review.md"
        lines = [
            "# ASR 纪要 vs 金标准 — 人工校对稿",
            f"> ASR: Faster-Whisper base | LLM: qwen3.5:4b | 标注转录: AliMeeting",
            "",
            f"共 {len(asr_results)} 场会议",
            "",
        ]
        for item in asr_results:
            mid = item["meeting_id"]
            g = gold.get(mid, {})
            lines.append("=" * 70)
            lines.append(f"## [{mid}]")
            lines.append(f"ASR 转录长度: {item['transcript_len']} 字 | "
                         f"金标准转录长度: {g.get('transcript_len', 0)} 字")
            lines.append("=" * 70)
            lines.append("")
            lines.append("### ASR 纪要")
            lines.append(item["minutes"])
            lines.append("")
            lines.append("---")
            lines.append("### 金标准纪要（对照）")
            lines.append(g.get("minutes", ""))
            lines.append("")
            lines.append("### 校对检查项")
            lines.append("- [ ] ASR 纪要是否遗漏了重要讨论点？")
            lines.append("- [ ] ASR 纪要有无事实错误/幻觉？")
            lines.append("- [ ] 待办事项是否合理？")
            lines.append("- [ ] 决议是否准确？")
            lines.append("")
            lines.append("---")
            lines.append("")

        review_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"校对稿已保存到 {review_path}")


if __name__ == "__main__":
    main()
