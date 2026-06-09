"""ASR 评估脚本 — 用 AliMeeting 近场数据测试 ASR 准确率

用法：
    python evaluation/asr_eval.py                     # 跑前 3 个文件试试
    python evaluation/asr_eval.py --all               # 跑全部 25 个文件
    python evaluation/asr_eval.py --file R8001_M8004  # 跑指定会议
"""

import json
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from engines.asr_engine import ASREngine
from jiwer import cer


def load_reference(json_path: str | Path) -> dict:
    """加载解析好的标注 JSON，返回 {文件名前缀: 参考文本}"""
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    refs = {}
    for item in data:
        # "R8001_M8004_N_SPK8013.TextGrid" → "R8001_M8004_N_SPK8013"
        prefix = item["file"].replace(".TextGrid", "")
        refs[prefix] = item["full_text_clean"]
    return refs


def match_audio_to_ref(
    audio_dir: Path, refs: dict
) -> list[tuple[str, Path, str]]:
    """匹配音频文件和参考文本，返回 [(会议名, wav路径, 参考文本)]"""
    matched = []
    for wav in sorted(audio_dir.glob("*.wav")):
        prefix = wav.stem  # "R8001_M8004_N_SPK8013"
        if prefix in refs:
            matched.append((prefix, wav, refs[prefix]))
    return matched


def run_asr_and_evaluate(asr: ASREngine, audio_path: Path, reference: str) -> dict:
    """对单个音频跑 ASR + 算 CER"""
    t0 = time.time()

    print(f"    ASR 转写中...", end=" ", flush=True)
    segments, duration = asr.transcribe(str(audio_path))
    hypothesis = " ".join(seg["text"] for seg in segments)

    elapsed = time.time() - t0
    ref_len = len(reference)
    hyp_len = len(hypothesis)

    error_rate = cer(reference, hypothesis)

    return {
        "duration_sec": duration,
        "duration_min": round(duration / 60, 1),
        "ref_chars": ref_len,
        "hyp_chars": hyp_len,
        "cer": round(error_rate, 4),
        "cer_pct": f"{error_rate:.2%}",
        "elapsed_sec": round(elapsed, 1),
        "reference": reference,
        "hypothesis": hypothesis,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ASR 评估 — AliMeeting 近场数据")
    parser.add_argument("--all", action="store_true", help="跑全部 25 个文件")
    parser.add_argument("--file", type=str, help="指定会议前缀，如 R8001_M8004")
    parser.add_argument("--limit", type=int, default=3, help="跑前 N 个文件（默认 3）")
    parser.add_argument("--skip", type=int, default=0, help="跳过前 N 个文件（配合 --limit 接续跑）")
    args = parser.parse_args()

    # 路径
    audio_dir = BASE_DIR / "data" / "alimeeting" / "Eval_Ali" / "Eval_Ali_near" / "audio_dir"
    ref_json = BASE_DIR / "evaluation" / "alimeeting_near_parsed.json"

    if not audio_dir.exists():
        print(f"音频目录不存在: {audio_dir}")
        return
    if not ref_json.exists():
        print(f"参考文本不存在: {ref_json}")
        return

    # 加载参考文本
    print("加载参考文本...")
    refs = load_reference(ref_json)
    print(f"  共 {len(refs)} 个参考文本")

    # 匹配音频和参考文本
    matched = match_audio_to_ref(audio_dir, refs)
    print(f"  匹配到 {len(matched)} 个音频文件\n")

    if not matched:
        print("没有匹配的音频文件！")
        return

    # 筛选
    if args.file:
        matched = [(n, p, r) for n, p, r in matched if args.file in n]
        print(f"  筛选 '{args.file}' → {len(matched)} 个文件\n")
    else:
        if args.skip:
            print(f"  跳过前 {args.skip} 个文件\n")
            matched = matched[args.skip:]
        if not args.all:
            matched = matched[:args.limit]
            print(f"  限制前 {args.limit} 个文件（加 --all 跑全部）\n")

    # 初始化 ASR
    print("初始化 ASR 引擎（首次加载模型可能较慢）...")
    asr = ASREngine()
    print("  ASR 引擎就绪\n")

    # 逐个跑
    results = []
    for i, (name, wav_path, ref_text) in enumerate(matched, 1):
        wav_size_mb = round(wav_path.stat().st_size / 1024 / 1024, 1)
        print(f"[{i}/{len(matched)}] {name}")
        print(f"    音频: {wav_path.name} ({wav_size_mb}MB)")

        result = run_asr_and_evaluate(asr, wav_path, ref_text)
        results.append({"name": name, **result})

        print(f"    时长: {result['duration_min']}min | "
              f"参考{result['ref_chars']}字 | ASR{result['hyp_chars']}字")
        print(f"    CER: {result['cer_pct']}")
        print(f"    耗时: {result['elapsed_sec']}s")
        print()

    # 汇总
    print("=" * 60)
    print("汇总结果")
    print("=" * 60)
    cers = [r["cer"] for r in results]
    avg_cer = sum(cers) / len(cers) if cers else 0
    print(f"  平均 CER: {avg_cer:.2%}")
    print(f"  最高 CER: {max(cers):.2%}")
    print(f"  最低 CER: {min(cers):.2%}")
    print(f"  评估文件数: {len(results)}")

    # 保存结果
    out_path = BASE_DIR / "evaluation" / "asr_eval_results_near.json"
    summary = {
        "dataset": "AliMeeting Eval Near",
        "num_files": len(results),
        "avg_cer": round(avg_cer, 4),
        "max_cer": round(max(cers), 4),
        "min_cer": round(min(cers), 4),
        "results": results,
    }
    out_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n结果已保存到 {out_path}")


if __name__ == "__main__":
    main()
