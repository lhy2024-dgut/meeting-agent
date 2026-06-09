"""ASR 远场快速评估脚本 — 启用 VAD 过滤 + 分段处理

使用 VAD (Voice Activity Detection) 过滤静音段，大幅减少 CPU 处理量。
用法：
    python evaluation/asr_eval_far.py --limit 2          # 跑前 2 个
    python evaluation/asr_eval_far.py --file R8001_M8004 # 跑指定会议
    python evaluation/asr_eval_far.py --all              # 全部
"""

import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from faster_whisper import WhisperModel
import config
from jiwer import cer


def load_far_reference(json_path: str | Path) -> dict:
    """加载解析好的远场标注 JSON，返回 {会议名: 参考文本}"""
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    refs = {}
    for item in data:
        prefix = item["file"].replace(".TextGrid", "")
        refs[prefix] = item["full_text_clean"]
    return refs


def match_audio_to_ref(audio_dir: Path, refs: dict) -> list[tuple[str, Path, str]]:
    """匹配远场音频文件和参考文本"""
    matched = []
    for wav in sorted(audio_dir.glob("*.wav")):
        meeting_prefix = "_".join(wav.stem.split("_")[:2])
        if wav.stem in refs:
            matched.append((wav.stem, wav, refs[wav.stem]))
        elif meeting_prefix in refs:
            matched.append((meeting_prefix, wav, refs[meeting_prefix]))
        else:
            print(f"  [X] 未匹配: {wav.stem} (尝试: {meeting_prefix})")
    return matched


def run_asr_with_vad(model, audio_path: Path, reference: str, name: str) -> dict:
    """用 VAD 过滤跑 ASR，只处理有语音的段落"""
    t0 = time.time()
    dur_sec = 0

    print(f"    ASR 转写中 (VAD 开启)...", end=" ", flush=True)

    # 直接调用 model.transcribe 开启 VAD 过滤
    segments_raw, info = model.transcribe(
        str(audio_path),
        language=config.WHISPER_LANGUAGE,
        beam_size=5,
        vad_filter=True,                    # 开启 VAD 过滤静音
        vad_parameters=dict(
            threshold=0.5,                  # VAD 阈值，默认 0.5
            min_speech_duration_ms=250,     # 最短语音段 250ms
            max_speech_duration_s=30,       # 最长语音段 30s（避免过长的 VAD clip）
            min_silence_duration_ms=500,    # 最短静音段 500ms
        ),
        condition_on_previous_text=True,
    )

    text_parts = []
    for seg in segments_raw:
        text_parts.append(seg.text.strip())
    hypothesis = " ".join(text_parts)
    dur_sec = info.duration

    elapsed = time.time() - t0
    ref_len = len(reference)
    hyp_len = len(hypothesis)
    error_rate = cer(reference, hypothesis)

    return {
        "name": name,
        "duration_sec": dur_sec,
        "duration_min": round(dur_sec / 60, 1),
        "ref_chars": ref_len,
        "hyp_chars": hyp_len,
        "cer": round(error_rate, 4),
        "cer_pct": f"{error_rate:.2%}",
        "elapsed_sec": round(elapsed, 1),
        "rtf": round(elapsed / dur_sec, 3) if dur_sec > 0 else 0,
        "vad_enabled": True,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ASR 评估 — AliMeeting 远场数据 (VAD 加速)")
    parser.add_argument("--all", action="store_true", help="跑全部 8 个远场文件")
    parser.add_argument("--file", type=str, help="指定会议前缀，如 R8001_M8004")
    parser.add_argument("--limit", type=int, default=99, help="跑前 N 个文件")
    parser.add_argument("--output", type=str, default="asr_eval_results_far.json",
                        help="输出文件名")
    args = parser.parse_args()

    audio_dir = BASE_DIR / "data" / "alimeeting" / "Eval_Ali" / "Eval_Ali_far" / "audio_dir"
    ref_json = BASE_DIR / "evaluation" / "alimeeting_far_parsed.json"
    output_path = BASE_DIR / "evaluation" / args.output

    if not audio_dir.exists():
        print(f"[X] 音频目录不存在: {audio_dir}")
        return
    if not ref_json.exists():
        print(f"[X] 参考文本不存在: {ref_json}")
        return

    # 加载参考文本
    print("加载远场参考文本...")
    refs = load_far_reference(ref_json)
    print(f"  [OK] {len(refs)} 个会议参考文本")

    # 匹配音频
    matched = match_audio_to_ref(audio_dir, refs)
    print(f"  [OK] 匹配到 {len(matched)} 个音频文件\n")

    if not matched:
        return

    # 筛选
    if args.file:
        matched = [(n, p, r) for n, p, r in matched if args.file in n]
    if not args.all:
        matched = matched[:args.limit]

    print(f"待处理: {len(matched)} 个会议")
    for name, wav_path, ref_text in matched:
        mb = wav_path.stat().st_size / 1024 / 1024
        print(f"  {name}: {mb:.0f}MB, {len(ref_text)} 参考字数")
    print()

    # 加载模型（直接用 WhisperModel）
    print("加载 Faster-Whisper 模型...")
    model = WhisperModel(
        config.WHISPER_MODEL,
        device=config.WHISPER_DEVICE,
        compute_type=config.WHISPER_COMPUTE_TYPE,
    )
    print("  [OK] 模型就绪\n")

    # 逐个跑
    results = []
    for i, (name, wav_path, ref_text) in enumerate(matched, 1):
        mb = round(wav_path.stat().st_size / 1024 / 1024, 1)
        print(f"[{i}/{len(matched)}] {name}")
        print(f"    音频: {wav_path.name} ({mb}MB)")

        result = run_asr_with_vad(model, wav_path, ref_text, name)
        results.append(result)

        hyp_chars_shown = min(len(result.get("hypothesis_preview", "")), 100)
        print(f"    时长: {result['duration_min']}min | RTF: {result['rtf']}x")
        print(f"    参考{result['ref_chars']}字 -> ASR{result['hyp_chars']}字")
        print(f"    CER: {result['cer_pct']}  (耗时: {result['elapsed_sec']}s)")
        print()

    # 汇总
    print("=" * 60)
    print("汇总结果")
    print("=" * 60)
    cers = [r["cer"] for r in results]
    avg_cer = sum(cers) / len(cers) if cers else 0
    print(f"  平均 CER:     {avg_cer:.2%}")
    print(f"  最高 CER:     {max(cers):.2%}")
    print(f"  最低 CER:     {min(cers):.2%}")
    print(f"  评估会议数:   {len(results)}")
    total_ref = sum(r["ref_chars"] for r in results)
    total_hyp = sum(r["hyp_chars"] for r in results)
    print(f"  总参考字数:   {total_ref}")
    print(f"  总 ASR 字数:  {total_hyp}")

    # 保存结果
    summary = {
        "dataset": "AliMeeting Eval Far",
        "num_files": len(results),
        "avg_cer": round(avg_cer, 4),
        "max_cer": round(max(cers), 4),
        "min_cer": round(min(cers), 4),
        "total_ref_chars": total_ref,
        "total_hyp_chars": total_hyp,
        "vad_enabled": True,
        "results": results,
    }
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n结果已保存到 {output_path}")


if __name__ == "__main__":
    main()
