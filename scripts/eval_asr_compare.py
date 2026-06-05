# -*- coding: utf-8 -*-
"""ASR 引擎对比评估脚本 — Whisper vs SenseVoice

直接对比每个音频文件的 ASR 转写 vs TextGrid 金标准，
不使用时间戳对齐，直接对整段音频的转写结果做 CER/WER 计算。

用法:
    python scripts/eval_asr_compare.py
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


def parse_textgrid(filepath: str) -> list[dict]:
    """解析 Praat TextGrid 文件"""
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


def compute_cer(reference: str, hypothesis: str) -> float:
    """计算字错误率 (Character Error Rate)"""
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


def compute_wer(reference: str, hypothesis: str) -> float:
    """计算词错误率 (Word Error Rate)"""
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


def get_meeting_id(filename: str) -> str:
    parts = filename.replace(".wav", "").replace(".TextGrid", "").split("_")
    return f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else filename


def run_engine_eval(engine_name, asr, audio_dir, textgrid_dir):
    """用指定引擎评估所有音频文件

    评估方式：逐文件对比（AliMeeting 近场录音 = 每个文件一个说话人）
    - 每个 .wav 文件是单个说话人的近场录音
    - ASR 逐文件转写，直接对比该说话人的 TextGrid 金标准
    - 无需说话人分离
    """
    print(f"\n{'='*70}")
    print(f"  🎤 {engine_name} 评估")
    print(f"  📐 对比方式: 逐文件转写 vs 对应说话人 TextGrid 金标准")
    print(f"{'='*70}")

    audio_files = sorted(f for f in os.listdir(audio_dir) if f.endswith(".wav"))
    # 按会议分组（仅用于展示）
    meetings = {}
    for af in audio_files:
        mid = get_meeting_id(af)
        meetings.setdefault(mid, []).append(af)

    results = []
    total_cer = 0.0
    total_wer = 0.0
    count = 0
    total_time = 0.0
    total_audio = 0.0

    for mid, files in sorted(meetings.items()):
        print(f"\n  📁 会议 {mid}（{len(files)} 个说话人）")

        for af in files:
            speaker_id = af.replace(".wav", "")
            tg_path = os.path.join(textgrid_dir, speaker_id + ".TextGrid")
            if not os.path.exists(tg_path):
                print(f"    ⚠️ {speaker_id}: 无 TextGrid，跳过")
                continue

            # 解析金标准
            gold_intervals = parse_textgrid(tg_path)
            gold_text = " ".join(item["text"] for item in gold_intervals)

            # 转写该说话人的音频文件
            audio_path = os.path.join(audio_dir, af)
            print(f"    🎙️ {speaker_id}: 转写...", end="", flush=True)
            t0 = time.time()
            segments, duration = asr.transcribe(audio_path)
            elapsed = time.time() - t0
            total_time += elapsed
            total_audio += duration
            asr_text = " ".join(seg["text"] for seg in segments)

            # 计算 CER/WER
            cer = compute_cer(gold_text, asr_text)
            wer = compute_wer(gold_text, asr_text)

            total_cer += cer
            total_wer += wer
            count += 1

            print(f" CER={cer:.1%} WER={wer:.1%} ({elapsed:.1f}s, {duration:.0f}s音频, "
                  f"金标准{len(gold_text)}字 vs ASR{len(asr_text)}字)")

            results.append({
                "meeting_id": mid,
                "speaker": speaker_id,
                "cer": round(cer, 4),
                "wer": round(wer, 4),
                "gold_len": len(gold_text),
                "asr_len": len(asr_text),
                "audio_duration": round(duration, 1),
                "process_time": round(elapsed, 1),
                "segments_count": len(segments),
            })

    avg_cer = total_cer / count if count else 0
    avg_wer = total_wer / count if count else 0
    rtf = total_time / total_audio if total_audio else 0

    summary = {
        "engine": engine_name,
        "total_files": count,
        "avg_cer": round(avg_cer, 4),
        "avg_wer": round(avg_wer, 4),
        "total_process_time": round(total_time, 1),
        "total_audio_duration": round(total_audio, 1),
        "rtf": round(rtf, 4),
    }

    print(f"\n  📊 {engine_name} 汇总")
    print(f"  {'─'*40}")
    print(f"  评估文件数:     {count}")
    print(f"  平均 CER:       {avg_cer:.1%}")
    print(f"  平均 WER:       {avg_wer:.1%}")
    print(f"  总处理时间:     {total_time:.1f}s")
    print(f"  总音频时长:     {total_audio:.1f}s")
    print(f"  RTF (实时率):   {rtf:.3f} ({'实时' if rtf < 1 else '慢于实时'})")

    return {"summary": summary, "details": results}


def main():
    data_dir = r"C:\Users\Administrator\Downloads\Eval_Ali\Eval_Ali\Eval_Ali_near"
    audio_dir = os.path.join(data_dir, "audio_dir")
    textgrid_dir = os.path.join(data_dir, "textgrid_dir")
    output_dir = os.path.join(ROOT_DIR, "evaluation", "results")

    if not os.path.exists(audio_dir):
        print(f"❌ 音频目录不存在: {audio_dir}")
        return
    if not os.path.exists(textgrid_dir):
        print(f"❌ TextGrid 目录不存在: {textgrid_dir}")
        return

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║       ASR 引擎对比评估 — Whisper vs SenseVoice             ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # ── Whisper ──
    print("\n⏳ 加载 Faster-Whisper 模型...")
    from engines.asr_engine import ASREngine
    whisper_asr = ASREngine()
    whisper_result = run_engine_eval("Faster-Whisper (base)", whisper_asr, audio_dir, textgrid_dir)

    # ── SenseVoice ──
    print("\n⏳ 加载 SenseVoice 模型...")
    from engines.sensevoice_engine import SenseVoiceEngine
    sv_asr = SenseVoiceEngine()
    sv_result = run_engine_eval("SenseVoice-Small", sv_asr, audio_dir, textgrid_dir)

    # ── 对比汇总 ──
    ws = whisper_result["summary"]
    ss = sv_result["summary"]

    print(f"\n{'═'*70}")
    print(f"  📊 ASR 引擎对比汇总")
    print(f"{'═'*70}")
    print(f"  {'指标':<18} {'Whisper-base':<16} {'SenseVoice':<16} {'差异':<12}")
    print(f"  {'─'*60}")

    cer_diff = ws["avg_cer"] - ss["avg_cer"]
    wer_diff = ws["avg_wer"] - ss["avg_wer"]
    rtf_diff = ws["rtf"] - ss["rtf"]

    cer_winner = "✅ SV" if cer_diff > 0 else ("✅ Whisper" if cer_diff < 0 else "─")
    wer_winner = "✅ SV" if wer_diff > 0 else ("✅ Whisper" if wer_diff < 0 else "─")
    rtf_winner = "✅ SV" if rtf_diff > 0 else ("✅ Whisper" if rtf_diff < 0 else "─")

    print(f"  {'CER':<18} {ws['avg_cer']:<16.1%} {ss['avg_cer']:<16.1%} {cer_winner}")
    print(f"  {'WER':<18} {ws['avg_wer']:<16.1%} {ss['avg_wer']:<16.1%} {wer_winner}")
    print(f"  {'RTF (实时率)':<18} {ws['rtf']:<16.3f} {ss['rtf']:<16.3f} {rtf_winner}")
    print(f"  {'处理时间(s)':<18} {ws['total_process_time']:<16.1f} {ss['total_process_time']:<16.1f}")
    print(f"  {'音频时长(s)':<18} {ws['total_audio_duration']:<16.1f} {ss['total_audio_duration']:<16.1f}")

    # ── 逐文件对比表 ──
    print(f"\n  📋 逐文件 CER 对比")
    print(f"  {'─'*65}")
    print(f"  {'Speaker':<32} {'Whisper':<12} {'SenseVoice':<12} {'更好':<8}")
    print(f"  {'─'*65}")

    for wd, sd in zip(whisper_result["details"], sv_result["details"]):
        spk = wd["speaker"]
        w_cer = wd["cer"]
        s_cer = sd["cer"]
        better = "SV" if s_cer < w_cer else ("Whisper" if w_cer < s_cer else "─")
        print(f"  {spk:<32} {w_cer:<12.1%} {s_cer:<12.1%} {better}")

    # ── 保存结果 ──
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "asr_compare_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "whisper": whisper_result,
            "sensevoice": sv_result,
            "comparison": {
                "cer_diff": round(cer_diff, 4),
                "wer_diff": round(wer_diff, 4),
                "rtf_diff": round(rtf_diff, 4),
                "cer_winner": cer_winner.strip(),
                "wer_winner": wer_winner.strip(),
                "rtf_winner": rtf_winner.strip(),
            },
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 结果已保存: {output_path}")
    print(f"{'═'*70}")


if __name__ == "__main__":
    main()
