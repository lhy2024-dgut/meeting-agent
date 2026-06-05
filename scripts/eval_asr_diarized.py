# -*- coding: utf-8 -*-
"""ASR + 说话人分离 联合评估脚本

流程：每个音频文件（单说话人近场录音）
1. ASR 转写
2. 说话人分离（VAD + CAM++ 聚类）
3. 用说话人标签过滤出目标说话人的转写段
4. 与 TextGrid 金标准对比 CER/WER

用法:
    python scripts/eval_asr_diarized.py
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_textgrid(filepath):
    intervals = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    pattern = r'intervals\s*\[\d+\]:\s*xmin\s*=\s*([\d.]+)\s*xmax\s*=\s*([\d.]+)\s*text\s*=\s*"([^"]*)"'
    for match in re.finditer(pattern, content):
        xmin, xmax, text = match.groups()
        text = text.strip()
        if text:
            intervals.append({"start": float(xmin), "end": float(xmax), "text": text})
    return intervals


def compute_cer(reference, hypothesis):
    ref_chars = list(reference.replace(" ", ""))
    hyp_chars = list(hypothesis.replace(" ", ""))
    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0
    n, m = len(ref_chars), len(hyp_chars)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_chars[i - 1] == hyp_chars[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + 1)
    return dp[n][m] / len(ref_chars)


def compute_wer(reference, hypothesis):
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    n, m = len(ref_words), len(hyp_words)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + 1)
    return dp[n][m] / len(ref_words)


def get_meeting_id(filename):
    parts = filename.replace(".wav", "").replace(".TextGrid", "").split("_")
    return f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else filename


def main():
    data_dir = r"C:\Users\Administrator\Downloads\Eval_Ali\Eval_Ali\Eval_Ali_near"
    audio_dir = os.path.join(data_dir, "audio_dir")
    textgrid_dir = os.path.join(data_dir, "textgrid_dir")
    output_dir = os.path.join(ROOT_DIR, "evaluation", "results")

    if not os.path.exists(audio_dir) or not os.path.exists(textgrid_dir):
        print("❌ 数据目录不存在")
        return

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║    ASR + 说话人分离 联合评估                                ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # 加载模型
    print("\n⏳ 加载模型...")
    from engines.asr_engine import ASREngine
    from engines.diarization_engine import DiarizationEngine, _assign_speaker_to_segments

    asr = ASREngine()
    diarizer = DiarizationEngine(max_speakers=4, merge_gap_ms=2000)

    audio_files = sorted(f for f in os.listdir(audio_dir) if f.endswith(".wav"))
    meetings = {}
    for af in audio_files:
        mid = get_meeting_id(af)
        meetings.setdefault(mid, []).append(af)

    results = []

    for mid, files in sorted(meetings.items()):
        print(f"\n  📁 会议 {mid}（{len(files)} 个说话人）")

        # 1. ASR 转写第一个音频（所有 speaker 共享同一段音频）
        audio_path = os.path.join(audio_dir, files[0])
        print(f"    🎙️ ASR 转写...", end="", flush=True)
        t0 = time.time()
        segments, duration = asr.transcribe(audio_path)
        asr_time = time.time() - t0
        print(f" 完成 ({asr_time:.1f}s, {len(segments)} 段)")

        # 2. 说话人分离
        print(f"    🗣️ 说话人分离...", end="", flush=True)
        t0 = time.time()
        intervals, num_speakers = diarizer.diarize(audio_path)
        diar_time = time.time() - t0
        print(f" 完成 ({diar_time:.1f}s, {num_speakers} 人)")

        # 3. 给 ASR 段分配说话人标签
        if intervals:
            _assign_speaker_to_segments(segments, intervals)
        else:
            for seg in segments:
                seg["speaker"] = "SPEAKER_0"

        # 4. 逐文件评估
        for af in files:
            speaker_id = af.replace(".wav", "")
            tg_path = os.path.join(textgrid_dir, speaker_id + ".TextGrid")
            if not os.path.exists(tg_path):
                continue

            gold_intervals = parse_textgrid(tg_path)
            gold_text = " ".join(item["text"] for item in gold_intervals)

            # 策略：用时间戳对齐 + 说话人标签双重过滤
            # 找出与该说话人金标准时间段重叠最多的 ASR 说话人标签
            speaker_overlap = {}  # speaker_label → 总重叠时长
            for gold in gold_intervals:
                g_start = gold["start"] * 1000  # → ms
                g_end = gold["end"] * 1000
                for seg in segments:
                    s_start = seg.get("start", 0) * 1000
                    s_end = seg.get("end", 0) * 1000
                    overlap = max(0, min(g_end, s_end) - max(g_start, s_start))
                    if overlap > 0:
                        spk = seg.get("speaker", "SPEAKER_0")
                        speaker_overlap[spk] = speaker_overlap.get(spk, 0) + overlap

            # 选择重叠最大的说话人作为目标说话人
            if speaker_overlap:
                target_speaker = max(speaker_overlap, key=speaker_overlap.get)
            else:
                target_speaker = "SPEAKER_0"

            # 过滤出目标说话人的 ASR 文本
            target_segments = [s for s in segments if s.get("speaker") == target_speaker]
            asr_text = " ".join(s["text"] for s in target_segments)

            # 如果过滤后为空，回退到全部文本
            if not asr_text.strip():
                asr_text = " ".join(s["text"] for s in segments)

            cer = compute_cer(gold_text, asr_text)
            wer = compute_wer(gold_text, asr_text)

            print(f"    ✅ {speaker_id}: CER={cer:.1%} WER={wer:.1%} "
                  f"(目标={target_speaker}, 金标准{len(gold_text)}字 vs ASR{len(asr_text)}字)")

            results.append({
                "meeting_id": mid,
                "speaker": speaker_id,
                "target_speaker": target_speaker,
                "num_speakers": num_speakers,
                "cer": round(cer, 4),
                "wer": round(wer, 4),
                "gold_len": len(gold_text),
                "asr_len": len(asr_text),
                "asr_time": round(asr_time, 1),
                "diar_time": round(diar_time, 1),
            })

    # 汇总
    if results:
        avg_cer = sum(r["cer"] for r in results) / len(results)
        avg_wer = sum(r["wer"] for r in results) / len(results)
        total_asr_time = sum(r["asr_time"] for r in results) / len(set(r["meeting_id"] for r in results))
        total_diar_time = sum(r["diar_time"] for r in results) / len(set(r["meeting_id"] for r in results))

        print(f"\n{'═'*70}")
        print(f"  📊 ASR + 说话人分离 联合评估汇总")
        print(f"{'═'*70}")
        print(f"  评估文件数:     {len(results)}")
        print(f"  平均 CER:       {avg_cer:.1%}")
        print(f"  平均 WER:       {avg_wer:.1%}")
        print(f"  平均 ASR 时间:  {total_asr_time:.1f}s/会议")
        print(f"  平均分离时间:   {total_diar_time:.1f}s/会议")

        # 与无分离的基线对比
        baseline_path = os.path.join(output_dir, "asr_compare_results.json")
        if os.path.exists(baseline_path):
            with open(baseline_path, "r", encoding="utf-8") as f:
                baseline = json.load(f)
            w_cer = baseline["whisper"]["summary"]["avg_cer"]
            print(f"\n  📈 对比基线 (Whisper 无分离):")
            print(f"  {'─'*50}")
            print(f"  {'方法':<25} {'CER':<12} {'WER':<12}")
            print(f"  {'─'*50}")
            print(f"  {'Whisper 无分离':<25} {w_cer:<12.1%} -")
            print(f"  {'Whisper + 分离':<25} {avg_cer:<12.1%} {avg_wer:.1%}")
            diff = w_cer - avg_cer
            print(f"  {'CER 改善':<25} {'↓' + f'{diff:.1%}' if diff > 0 else '↑' + f'{-diff:.1%}':<12}")

        # 保存
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "asr_diarized_results.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total_files": len(results),
                    "avg_cer": round(avg_cer, 4),
                    "avg_wer": round(avg_wer, 4),
                },
                "details": results,
            }, f, ensure_ascii=False, indent=2)
        print(f"\n  💾 结果已保存: {output_path}")
        print(f"{'═'*70}")


if __name__ == "__main__":
    main()
