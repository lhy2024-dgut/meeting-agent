"""术语词表注入 ASR 对比测试

直接测试 ASR 在有无术语词表下的专有名词识别效果。
使用测试脚本材料①作为参考文本。

用法：
  python evaluation/test_term_injection.py
"""

import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from engines.asr_engine import ASREngine
from jiwer import cer

# ── 测试材料 ──
AUDIO_PATH = BASE_DIR / "tests" / "fixtures" / "audio" / "测试样本1（科技）.mp3"

REFERENCE_TEXT = (
    "张伟，Omega-3项目现在到什么阶段了？上周你说DataFlow平台的接口已经联调完了，"
    "这周能按时上线吗？李娜那边的CloudLab团队反馈SuperNode模块有个性能瓶颈，"
    "王建国正在排查。如果这周修不完，Project-X的交付可能要延期。"
    "建议明天拉个会，把AI-Squad小组也叫上，一起对齐一下排期。"
    "会议纪要智能体这边也要同步一份给后端团队。"
)

TERMS = [
    "张伟",
    "Omega-3项目",
    "DataFlow平台",
    "CloudLab团队",
    "SuperNode模块",
    "Project-X",
    "AI-Squad小组",
    "会议纪要智能体",
]


def get_duration_seconds(wav_path: Path) -> float:
    """估算音频时长"""
    import wave
    try:
        with wave.open(str(wav_path), "r") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        import subprocess
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(wav_path)],
                capture_output=True, text=True, timeout=10
            )
            return float(r.stdout.strip())
        except Exception:
            print("  [WARN] 无法获取音频时长")
            return 0


def check_terms(hypothesis: str, terms: list[str]) -> dict:
    """逐一检查每个专有名词是否被正确识别"""
    results = {}
    for term in terms:
        found = term.lower() in hypothesis.lower()
        results[term] = {
            "correct": found,
            "details": f"[OK] '{term}' 正确识别" if found else f"[X] '{term}' 未识别到"
        }
    return results


def run_test(asr: ASREngine, audio_path: Path, reference: str,
             terms: list[str] | None = None, label: str = "无词表") -> dict:
    """跑一次 ASR 测试"""
    print(f"\n{'=' * 50}")
    print(f"[{label}] 开始 ASR 转写")
    print(f"{'=' * 50}")

    initial_prompt = " ".join(terms) if terms else None
    if initial_prompt:
        print(f"  initial_prompt: {initial_prompt}")

    t0 = time.time()
    segments, duration = asr.transcribe(str(audio_path), initial_prompt=initial_prompt)
    hypothesis = " ".join(seg["text"] for seg in segments)
    elapsed = time.time() - t0

    error_rate = cer(reference, hypothesis)
    term_results = check_terms(hypothesis, TERMS)

    correct = sum(1 for v in term_results.values() if v["correct"])
    total = len(term_results)

    print(f"\n  ASR 输出: {hypothesis}")
    print(f"  CER: {error_rate:.2%}")
    print(f"  专有名词: {correct}/{total} 正确 ({correct/total*100:.1f}%)")
    print(f"  耗时: {elapsed:.1f}s")

    return {
        "label": label,
        "hypothesis": hypothesis,
        "cer": round(error_rate, 4),
        "cer_pct": f"{error_rate:.2%}",
        "correct_terms": correct,
        "total_terms": total,
        "term_accuracy": f"{correct}/{total}",
        "term_results": {k: v["correct"] for k, v in term_results.items()},
        "term_details": {k: v["details"] for k, v in term_results.items()},
        "elapsed_sec": round(elapsed, 1),
    }


def main():
    print("=" * 60)
    print("术语词表注入测试 — 专有名词识别对比")
    print("=" * 60)
    print(f"\n参考文本: {REFERENCE_TEXT}")
    print(f"专有名词: {TERMS}")
    print(f"音频文件: {AUDIO_PATH.name}")
    dur = get_duration_seconds(AUDIO_PATH)
    if dur:
        print(f"音频时长: {dur:.1f}s ({dur/60:.1f}min)")

    if not AUDIO_PATH.exists():
        print(f"[X] 音频文件不存在: {AUDIO_PATH}")
        return

    # 初始化 ASR
    print("\n初始化 ASR 引擎...")
    asr = ASREngine()
    print("  [OK] 引擎就绪")

    # 测试 1：不加词表
    result_no = run_test(asr, AUDIO_PATH, REFERENCE_TEXT, terms=None, label="不加词表")

    # 测试 2：加词表
    result_with = run_test(asr, AUDIO_PATH, REFERENCE_TEXT, terms=TERMS, label="加词表")

    # ── 结果对比 ──
    print("\n\n" + "=" * 60)
    print("测试结果对比")
    print("=" * 60)

    print(f"\n{'指标':<20} {'无词表':<20} {'有词表':<20} {'提升':<20}")
    print("-" * 80)
    print(f"{'CER':<20} {result_no['cer_pct']:<20} {result_with['cer_pct']:<20} "
          f"{'↓ ' + str(round((result_no['cer'] - result_with['cer']) * 100, 2)) + 'pp':<20}")
    print(f"{'专有名词正确率':<20} {result_no['term_accuracy']:<20} {result_with['term_accuracy']:<20} "
          f"{result_no['correct_terms']}/{result_no['total_terms']} → {result_with['correct_terms']}/{result_with['total_terms']}")
    print(f"{'耗时':<20} {result_no['elapsed_sec']}s{'':<12} {result_with['elapsed_sec']}s{'':<12}")

    print(f"\n\n--- 逐词对照 ---")
    print(f"{'词条':<20} {'无词表':<8} {'有词表':<8}")
    print("-" * 40)
    for term in TERMS:
        no_ok = "[OK]" if result_no["term_results"][term] else "[X]"
        with_ok = "[OK]" if result_with["term_results"][term] else "[X]"
        print(f"{term:<20} {no_ok:<8} {with_ok:<8}")

    # 保存结果 JSON
    summary = {
        "test_info": {
            "audio": str(AUDIO_PATH),
            "reference": REFERENCE_TEXT,
            "terms": TERMS,
        },
        "without_terms": result_no,
        "with_terms": result_with,
        "improvement": {
            "cer_drop_pp": round((result_no["cer"] - result_with["cer"]) * 100, 2),
            "term_accuracy_gain": f"{result_no['correct_terms']}/{result_no['total_terms']} → {result_with['correct_terms']}/{result_with['total_terms']}",
        },
    }

    out_path = BASE_DIR / "evaluation" / "term_injection_results.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细结果已保存到 {out_path}")


if __name__ == "__main__":
    main()
