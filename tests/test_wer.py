"""ASR 模型对比测试脚本 — 字错误率（CER）+ 耗时

用法：
  python tests/test_wer.py --audio path/to/audio.wav --ref "正确的转录文本"
  python tests/test_wer.py --audio path/to/audio.wav --ref-file path/to/ref.txt
  python tests/test_wer.py --audio path/to/audio.wav --ref "..." --terms "术语1,术语2"
  python tests/test_wer.py --audio tests/fixtures/audio/terms_test.wav --ref-file tests/fixtures/audio/terms_test_ref.txt

输出示例：
  ┌──────────────────────────────────────────────────────────┐
  │  模型               CER     时长    术语命中
  │  faster-whisper    12.3%   18.4s   7/10
  │  SenseVoiceSmall    8.1%   11.2s   9/10
  └──────────────────────────────────────────────────────────┘

依赖：pip install jiwer
"""

import argparse
import re
import sys
import time
from pathlib import Path

# ── 确保项目根目录在 PATH 中 ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── CER 计算 ──────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """去除标点、空格，保留中文字符和英文字母数字（小写）"""
    text = text.lower()
    text = re.sub(r"[^一-鿿A-Za-z0-9]", "", text)
    return text


def calculate_cer(reference: str, hypothesis: str) -> float:
    """字符错误率（Character Error Rate），适用于中文"""
    try:
        from jiwer import cer as jiwer_cer
        ref = _normalize(reference)
        hyp = _normalize(hypothesis)
        if not ref:
            return 0.0
        # jiwer cer 需要按字符 split
        return jiwer_cer(" ".join(ref), " ".join(hyp))
    except ImportError:
        # 手动实现 Levenshtein CER
        return _levenshtein_cer(_normalize(reference), _normalize(hypothesis))


def _levenshtein_cer(ref: str, hyp: str) -> float:
    if not ref:
        return 0.0
    n, m = len(ref), len(hyp)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            dp[j] = min(prev[j] + 1, dp[j - 1] + 1, prev[j - 1] + cost)
    return dp[m] / n


# ── 术语命中率 ────────────────────────────────────────────────────────────────

def count_term_hits(terms: list[str], hypothesis: str) -> tuple[int, int]:
    """返回 (命中数, 总数)"""
    hits = sum(1 for t in terms if t.lower() in hypothesis.lower())
    return hits, len(terms)


# ── 转写函数 ──────────────────────────────────────────────────────────────────

def transcribe_whisper(audio_path: str, terms: list[str] | None = None) -> tuple[str, float]:
    """用 faster-whisper 转写，返回 (文本, 耗时秒)"""
    from engines.asr_engine import ASREngine
    engine = ASREngine()
    t0 = time.time()
    segments, _ = engine.transcribe(audio_path, terms=terms)
    elapsed = time.time() - t0
    text = " ".join(seg["text"] for seg in segments)
    return text, elapsed


def transcribe_sensevoice(audio_path: str, terms: list[str] | None = None) -> tuple[str, float]:
    """用 SenseVoiceSmall 转写，返回 (文本, 耗时秒)"""
    from engines.sense_voice_engine import SenseVoiceEngine
    engine = SenseVoiceEngine()
    t0 = time.time()
    segments, _ = engine.transcribe(audio_path, terms=terms)
    elapsed = time.time() - t0
    text = " ".join(seg["text"] for seg in segments)
    return text, elapsed


# ── 主对比逻辑 ────────────────────────────────────────────────────────────────

def _sep(width=62):
    return "─" * width


def compare(
    audio_path: str,
    reference: str,
    terms: list[str] | None = None,
    models: list[str] | None = None,
):
    """对比所有指定模型，打印结果表格"""
    if models is None:
        models = ["faster-whisper", "SenseVoiceSmall"]

    print(f"\n{'═'*62}")
    print(f"  音频文件：{audio_path}")
    print(f"  参考文本：{reference[:60]}{'...' if len(reference)>60 else ''}")
    if terms:
        print(f"  术语词表：{', '.join(terms[:5])}{'...' if len(terms)>5 else ''} ({len(terms)} 条)")
    print(f"{'═'*62}")
    print(f"  {'模型':<22} {'CER':>7}  {'耗时':>8}  {'术语命中'}")
    print(f"  {_sep(58)}")

    results = {}
    for model in models:
        try:
            if model == "faster-whisper":
                hyp, elapsed = transcribe_whisper(audio_path, terms)
            elif model == "SenseVoiceSmall":
                hyp, elapsed = transcribe_sensevoice(audio_path, terms)
            else:
                print(f"  未知模型：{model}")
                continue

            cer_val = calculate_cer(reference, hyp)
            hits, total = count_term_hits(terms, hyp) if terms else (0, 0)
            hit_str = f"{hits}/{total}" if terms else "N/A"
            print(f"  {model:<22} {cer_val*100:>6.1f}%  {elapsed:>7.1f}s  {hit_str}")
            results[model] = {"cer": cer_val, "elapsed": elapsed, "hypothesis": hyp, "hits": hits}

        except Exception as e:
            print(f"  {model:<22} 错误：{e}")

    print(f"  {_sep(58)}")

    # 详细输出
    if results:
        print()
        for model, r in results.items():
            print(f"【{model}】转写结果：")
            print(f"  {r['hypothesis'][:200]}{'...' if len(r['hypothesis'])>200 else ''}")
            print()

    return results


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ASR 模型 CER 对比测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--audio", required=True, help="音频文件路径（.wav/.mp3 等）")
    parser.add_argument("--ref", default="", help="正确转录文本")
    parser.add_argument("--ref-file", default="", help="正确转录文本文件路径（与 --ref 二选一）")
    parser.add_argument(
        "--terms", default="",
        help="术语词表，逗号分隔，如 '量子纠缠,Transformer,项目代号'"
    )
    parser.add_argument(
        "--models", default="faster-whisper,SenseVoiceSmall",
        help="要测试的模型，逗号分隔（默认：faster-whisper,SenseVoiceSmall）"
    )
    parser.add_argument(
        "--no-terms", action="store_true",
        help="同时测试无术语词表版本（对比加/不加词表的差异）"
    )
    args = parser.parse_args()

    # 读取参考文本
    if args.ref_file:
        ref = Path(args.ref_file).read_text(encoding="utf-8").strip()
    elif args.ref:
        ref = args.ref
    else:
        print("错误：必须提供 --ref 或 --ref-file")
        sys.exit(1)

    # 解析术语
    terms = [t.strip() for t in args.terms.split(",") if t.strip()] if args.terms else None

    # 解析模型列表
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    # 不加词表的基线对比
    if args.no_terms and terms:
        print("\n▶ 不加术语词表（基线）")
        compare(args.audio, ref, terms=None, models=models)
        print("\n▶ 加入术语词表")

    compare(args.audio, ref, terms=terms, models=models)


if __name__ == "__main__":
    main()
