# -*- coding: utf-8 -*-
"""AliMeeting 评估脚本 — ASR 准确率 + RAG 召回率 联合评估

用法:
    python scripts/eval_alimeeting.py                          # 运行完整评估
    python scripts/eval_alimeeting.py --asr-only               # 仅评估 ASR
    python scripts/eval_alimeeting.py --rag-only                # 仅评估 RAG
    python scripts/eval_alimeeting.py --data-dir <path>         # 指定数据目录

数据目录结构:
    <data_dir>/
    ├── audio_dir/          # WAV 音频文件
    │   ├── R8003_M8001_N_SPK8001.wav
    │   └── ...
    └── textgrid_dir/       # TextGrid 标注文件（金标准）
        ├── R8003_M8001_N_SPK8001.TextGrid
        └── ...
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# 确保项目根目录在 sys.path 中
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Windows UTF-8
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ── TextGrid 解析器 ──

def parse_textgrid(filepath: str) -> list[dict]:
    """解析 Praat TextGrid 文件，返回 intervals 列表

    Returns:
        [{"start": float, "end": float, "text": str}, ...]
    """
    intervals = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 解析 intervals
    pattern = r'intervals\s*\[\d+\]:\s*xmin\s*=\s*([\d.]+)\s*xmax\s*=\s*([\d.]+)\s*text\s*=\s*"([^"]*)"'
    for match in re.finditer(pattern, content):
        xmin, xmax, text = match.groups()
        text = text.strip()
        if text:  # 跳过空 interval
            intervals.append({
                "start": float(xmin),
                "end": float(xmax),
                "text": text,
            })

    return intervals


def get_meeting_id_from_filename(filename: str) -> str:
    """从文件名提取会议 ID，如 R8003_M8001_N_SPK8001 → R8003_M8001"""
    # 文件名格式: R{room}_M{meeting}_N_SPK{speaker}
    parts = filename.replace(".wav", "").replace(".TextGrid", "").split("_")
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return filename


# ── ASR 评估 ──

def compute_cer(reference: str, hypothesis: str) -> float:
    """计算字错误率 (Character Error Rate)"""
    ref_chars = list(reference.replace(" ", ""))
    hyp_chars = list(hypothesis.replace(" ", ""))

    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0

    # 动态规划计算编辑距离
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
                dp[i][j] = min(
                    dp[i - 1][j] + 1,      # 删除
                    dp[i][j - 1] + 1,      # 插入
                    dp[i - 1][j - 1] + 1,  # 替换
                )

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
                dp[i][j] = min(
                    dp[i - 1][j] + 1,
                    dp[i][j - 1] + 1,
                    dp[i - 1][j - 1] + 1,
                )

    return dp[n][m] / len(ref_words)


def extract_speaker_text(asr_segments: list, gold_intervals: list) -> str:
    """根据 TextGrid 时间戳，从 ASR 输出中提取目标说话人的文本

    策略：对于每个 gold interval 的时间段，提取与该时间段重叠的 ASR segments
    """
    extracted = []
    for gold in gold_intervals:
        g_start = gold["start"]
        g_end = gold["end"]
        # 找与该时间段重叠的 ASR segments
        for seg in asr_segments:
            s_start = seg.get("start", 0)
            s_end = seg.get("end", 0)
            # 计算重叠比例
            overlap_start = max(g_start, s_start)
            overlap_end = min(g_end, s_end)
            overlap = max(0, overlap_end - overlap_start)
            seg_duration = s_end - s_start
            if seg_duration > 0 and overlap / seg_duration > 0.3:
                # 重叠超过 30% 就认为是该说话人的内容
                extracted.append(seg["text"])
                break
    return " ".join(extracted)


def eval_asr(audio_dir: str, textgrid_dir: str, output_dir: str, engine_name: str = "whisper") -> dict:
    """评估 ASR 准确率：用项目 ASR 转写音频，对比 TextGrid 金标准

    正确方法：用 TextGrid 时间戳从 ASR 输出中提取目标说话人的片段，再对比
    """
    print("\n" + "=" * 70)
    print(f"🎤 ASR 评估（{engine_name}）：对比 ASR 转写 vs TextGrid 金标准")
    print("=" * 70)

    if engine_name == "sensevoice":
        from engines.sensevoice_engine import SenseVoiceEngine
        asr = SenseVoiceEngine()
    else:
        from engines.asr_engine import ASREngine
        asr = ASREngine()

    # 按会议分组，同一会议只需转写一次
    meetings = {}  # meeting_id → [{audio_path, textgrid_path, speaker}]
    audio_files = sorted([f for f in os.listdir(audio_dir) if f.endswith(".wav")])

    for audio_file in audio_files:
        speaker_id = audio_file.replace(".wav", "")
        meeting_id = get_meeting_id_from_filename(audio_file)
        textgrid_file = os.path.join(textgrid_dir, speaker_id + ".TextGrid")

        if not os.path.exists(textgrid_file):
            print(f"  ⚠️ 跳过 {audio_file}（无对应 TextGrid）")
            continue

        if meeting_id not in meetings:
            meetings[meeting_id] = []
        meetings[meeting_id].append({
            "audio_path": os.path.join(audio_dir, audio_file),
            "textgrid_path": textgrid_file,
            "speaker": speaker_id,
        })

    print(f"  共 {len(meetings)} 场会议，{len(audio_files)} 个音频文件\n")
    print("  ⚡ 使用时间戳对齐：仅对比目标说话人的时间段\n")

    results = []
    total_cer = 0.0
    total_wer = 0.0
    count = 0

    for meeting_id, speakers in sorted(meetings.items()):
        print(f"  📁 会议 {meeting_id}（{len(speakers)} 个说话人）")
        meeting_ref = ""
        meeting_hyp = ""

        # 同一会议只需转写一次（所有 speaker 共享同一段音频）
        audio_path = speakers[0]["audio_path"]
        print(f"    🎙️ 转写 {meeting_id}...", end="", flush=True)
        t0 = time.time()
        asr_segments, duration = asr.transcribe(audio_path)
        elapsed = time.time() - t0
        print(f" 完成 ({elapsed:.1f}s, {duration:.0f}s音频, {len(asr_segments)} 段)")

        for spk in speakers:
            # 解析金标准
            gold_intervals = parse_textgrid(spk["textgrid_path"])
            gold_text = " ".join(item["text"] for item in gold_intervals)

            # 用时间戳从 ASR 输出中提取目标说话人的文本
            asr_text = extract_speaker_text(asr_segments, gold_intervals)

            if not asr_text.strip():
                # 如果提取为空，说明 ASR 没有覆盖该时间段
                cer = 1.0
                wer = 1.0
                print(f"    ⚠️ {spk['speaker']}: 提取为空（ASR 未覆盖该时间段）")
            else:
                # 计算该说话人的 CER/WER
                cer = compute_cer(gold_text, asr_text)
                wer = compute_wer(gold_text, asr_text)
                print(f"    ✅ {spk['speaker']}: CER={cer:.1%} WER={wer:.1%} (提取{len(asr_text)}字 vs 金标准{len(gold_text)}字)")

            print(f" CER={cer:.1%} WER={wer:.1%} ({elapsed:.1f}s, {duration:.0f}s音频)")

            results.append({
                "meeting_id": meeting_id,
                "speaker": spk["speaker"],
                "cer": round(cer, 4),
                "wer": round(wer, 4),
                "gold_len": len(gold_text),
                "asr_len": len(asr_text),
                "audio_duration": round(duration, 1),
                "process_time": round(elapsed, 1),
            })

            total_cer += cer
            total_wer += wer
            count += 1

            # 收集会议级文本
            meeting_ref += gold_text + " "
            meeting_hyp += asr_text + " "

        # 会议级 CER/WER
        m_cer = compute_cer(meeting_ref.strip(), meeting_hyp.strip())
        m_wer = compute_wer(meeting_ref.strip(), meeting_hyp.strip())
        print(f"    📊 会议级: CER={m_cer:.1%} WER={m_wer:.1%}")
        meeting_ref = ""
        meeting_hyp = ""

    # 汇总
    avg_cer = total_cer / count if count else 0
    avg_wer = total_wer / count if count else 0

    print(f"\n{'=' * 70}")
    print(f"  📊 ASR 评估汇总")
    print(f"{'=' * 70}")
    print(f"  评估文件数: {count}")
    print(f"  平均 CER:   {avg_cer:.1%}")
    print(f"  平均 WER:   {avg_wer:.1%}")

    # 保存结果
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"asr_eval_{engine_name}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "engine": engine_name,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_files": count,
                "avg_cer": round(avg_cer, 4),
                "avg_wer": round(avg_wer, 4),
            },
            "details": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 结果已保存: {output_path}")

    return {"avg_cer": avg_cer, "avg_wer": avg_wer, "details": results}


# ── RAG 评估 ──

def build_rag_from_textgrid(textgrid_dir: str, output_dir: str) -> list[dict]:
    """从 TextGrid 金标准构建 RAG 知识库，返回文档列表用于后续评估"""
    print("\n" + "=" * 70)
    print("📚 构建 RAG 知识库（基于 TextGrid 金标准）")
    print("=" * 70)

    # 按会议分组
    meetings = {}  # meeting_id → {speaker → text}
    textgrid_files = sorted([f for f in os.listdir(textgrid_dir) if f.endswith(".TextGrid")])

    for tg_file in textgrid_files:
        speaker_id = tg_file.replace(".TextGrid", "")
        meeting_id = get_meeting_id_from_filename(tg_file)

        intervals = parse_textgrid(os.path.join(textgrid_dir, tg_file))
        text = " ".join(item["text"] for item in intervals)

        if meeting_id not in meetings:
            meetings[meeting_id] = {}
        meetings[meeting_id][speaker_id] = text

    print(f"  共 {len(meetings)} 场会议，{len(textgrid_files)} 个 TextGrid 文件\n")

    # 构建文档列表
    documents = []
    for meeting_id, speakers in sorted(meetings.items()):
        full_text = " ".join(speakers.values())
        documents.append({
            "meeting_id": meeting_id,
            "text": full_text,
            "speakers": list(speakers.keys()),
            "char_count": len(full_text),
        })
        print(f"  📁 {meeting_id}: {len(speakers)} 说话人, {len(full_text)} 字")

    # 保存
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "rag_gold_documents.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 文档已保存: {output_path}")

    return documents


def generate_eval_qa(documents: list[dict]) -> list[dict]:
    """基于金标准文档自动生成评估 QA 对

    策略：从文档中提取关键信息，生成问答对
    """
    print("\n" + "=" * 70)
    print("❓ 自动生成评估 QA 对")
    print("=" * 70)

    qa_pairs = []

    for doc in documents:
        mid = doc["meeting_id"]
        text = doc["text"]

        # 策略1：用 LLM 生成 QA 对
        try:
            from engines.llm import get_llm
            llm = get_llm(temperature=0.3)

            prompt = f"""你是一个会议分析专家。请根据以下会议转录内容，生成 3 个问答对。

要求：
1. 问题应该自然，像真实用户会问的问题
2. 答案必须能从转录文本中直接找到依据
3. 每个问答对标注 1-3 个关键词（用于评估检索召回）

会议转录（前3000字）：
{text[:3000]}

请用 JSON 格式输出：
[
  {{"question": "...", "answer": "...", "keywords": ["关键词1", "关键词2"]}},
  ...
]
只输出 JSON，不要其他内容。"""

            response = llm.invoke(prompt)
            raw = response.content if hasattr(response, "content") else str(response)
            # 清理 markdown 包装
            raw = raw.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            llm_qa = json.loads(raw)
            for item in llm_qa:
                item["meeting_id"] = mid
                item["source"] = "llm_generated"
            qa_pairs.extend(llm_qa)
            print(f"  ✅ {mid}: LLM 生成 {len(llm_qa)} 个 QA 对")

        except Exception as e:
            print(f"  ⚠️ {mid}: LLM 生成失败 ({e})，使用规则生成")

            # 策略2：规则兜底
            # 提取可能的关键信息
            names = re.findall(r'[一-龥]{2,4}(?:说|认为|觉得|表示|提到)', text)
            numbers = re.findall(r'\d+(?:\.\d+)?(?:万|元|个|天|月|年|%|块)', text)

            if names:
                name = names[0][:-1]  # 去掉"说/认为"
                qa_pairs.append({
                    "question": f"{name}在会议中说了什么？",
                    "answer": f"{name}在会议中有发言",
                    "keywords": [name],
                    "meeting_id": mid,
                    "source": "rule_generated",
                })

            if numbers:
                qa_pairs.append({
                    "question": f"会议中提到了哪些数字/数据？",
                    "answer": f"会议中提到了 {', '.join(numbers[:3])}",
                    "keywords": [numbers[0]],
                    "meeting_id": mid,
                    "source": "rule_generated",
                })

            # 通用问题
            qa_pairs.append({
                "question": f"这场会议的主要内容是什么？",
                "answer": text[:200],
                "keywords": [mid.split("_")[0]],
                "meeting_id": mid,
                "source": "rule_generated",
            })

    # 保存
    print(f"\n  共生成 {len(qa_pairs)} 个 QA 对")
    return qa_pairs


def eval_rag_recall(documents: list[dict], qa_pairs: list[dict], top_k: int = 5) -> dict:
    """评估 RAG 检索召回率

    流程：
    1. 将金标准文档写入 RAG 知识库
    2. 用 QA 对的 question 检索
    3. 检查检索结果中是否包含 QA 对的 meeting_id（命中）
    """
    print("\n" + "=" * 70)
    print("🔍 RAG 召回率评估")
    print("=" * 70)

    # 写入知识库
    from rag.retriever import get_retriever
    from db.repository import MeetingRepository

    db = MeetingRepository()
    retriever = get_retriever()

    # 创建临时会议记录用于 RAG 索引
    print("\n  📝 写入金标准文档到 RAG 知识库...")
    doc_meeting_ids = []
    for doc in documents:
        mid_name = f"gold_{doc['meeting_id']}"
        # 创建会议记录
        meeting_id = db.create_meeting(
            title=mid_name,
            audio_path="",
            duration_category="medium",
            environment="unknown",
            file_hash=f"gold_{doc['meeting_id']}_{int(time.time())}",
        )
        # 写入 RAG 索引
        retriever.rebuild_meeting_index(
            meeting_id,
            transcript=doc["text"],
        )
        doc_meeting_ids.append({"gold_name": doc["meeting_id"], "db_id": meeting_id})
        print(f"    ✅ {doc['meeting_id']} → DB ID {meeting_id}")

    # 评估检索
    print(f"\n  🔎 检索评估（Top-{top_k}）...")
    hit_at_1 = 0
    hit_at_3 = 0
    hit_at_5 = 0
    total = len(qa_pairs)
    details = []

    for qa in qa_pairs:
        query = qa["question"]
        expected_mid = qa["meeting_id"]

        # 找到对应的 DB ID
        expected_db_id = None
        for dm in doc_meeting_ids:
            if dm["gold_name"] == expected_mid:
                expected_db_id = dm["db_id"]
                break

        if expected_db_id is None:
            continue

        # 检索
        results = retriever.search(query, top_k=top_k)
        retrieved_mids = [r["meeting_id"] for r in results]

        # 检查命中
        hit_positions = []
        for i, rid in enumerate(retrieved_mids):
            if rid == expected_db_id:
                hit_positions.append(i + 1)

        hit = len(hit_positions) > 0
        first_pos = hit_positions[0] if hit_positions else None

        if first_pos is not None:
            if first_pos <= 1:
                hit_at_1 += 1
            if first_pos <= 3:
                hit_at_3 += 1
            if first_pos <= 5:
                hit_at_5 += 1

        details.append({
            "question": query,
            "expected_meeting": expected_mid,
            "hit": hit,
            "first_hit_position": first_pos,
            "top_results": [
                {"meeting_id": r["meeting_id"], "score": r["score"], "type": r["chunk_type"]}
                for r in results[:3]
            ],
        })

        status = f"✅ @{first_pos}" if hit else "❌"
        print(f"    {status} '{query[:40]}...'")

    # 汇总
    recall_at_1 = hit_at_1 / total if total else 0
    recall_at_3 = hit_at_3 / total if total else 0
    recall_at_5 = hit_at_5 / total if total else 0

    # MRR
    mrr = 0
    for d in details:
        if d["first_hit_position"] is not None:
            mrr += 1.0 / d["first_hit_position"]
    mrr = mrr / total if total else 0

    print(f"\n{'=' * 70}")
    print(f"  📊 RAG 召回率评估汇总")
    print(f"{'=' * 70}")
    print(f"  评估 QA 对数: {total}")
    print(f"  Recall@1:     {recall_at_1:.1%} ({hit_at_1}/{total})")
    print(f"  Recall@3:     {recall_at_3:.1%} ({hit_at_3}/{total})")
    print(f"  Recall@5:     {recall_at_5:.1%} ({hit_at_5}/{total})")
    print(f"  MRR:          {mrr:.3f}")

    return {
        "recall_at_1": round(recall_at_1, 4),
        "recall_at_3": round(recall_at_3, 4),
        "recall_at_5": round(recall_at_5, 4),
        "mrr": round(mrr, 4),
        "total_qa": total,
        "details": details,
    }


# ── 主流程 ──

def main():
    parser = argparse.ArgumentParser(description="AliMeeting 评估脚本")
    parser.add_argument("--data-dir", default=r"C:\Users\Administrator\Downloads\Eval_Ali\Eval_Ali\Eval_Ali_near",
                        help="AliMeeting 数据目录")
    parser.add_argument("--output-dir", default="evaluation/results",
                        help="评估结果输出目录")
    parser.add_argument("--asr-only", action="store_true", help="仅评估 ASR")
    parser.add_argument("--rag-only", action="store_true", help="仅评估 RAG")
    parser.add_argument("--engine", default="whisper", choices=["whisper", "sensevoice", "both"],
                        help="ASR 引擎选择: whisper / sensevoice / both (对比)")
    parser.add_argument("--skip-llm-qa", action="store_true", help="跳过 LLM 生成 QA，使用规则生成")
    args = parser.parse_args()

    audio_dir = os.path.join(args.data_dir, "audio_dir")
    textgrid_dir = os.path.join(args.data_dir, "textgrid_dir")

    if not os.path.exists(audio_dir):
        print(f"❌ 音频目录不存在: {audio_dir}")
        return
    if not os.path.exists(textgrid_dir):
        print(f"❌ TextGrid 目录不存在: {textgrid_dir}")
        return

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         AliMeeting 评估 — ASR + RAG 联合评估               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  数据目录: {args.data_dir}")
    print(f"  输出目录: {args.output_dir}")

    results = {}

    # Step 1: ASR 评估
    if not args.rag_only:
        if args.engine == "both":
            # 对比两个引擎
            print("\n" + "🔥" * 35)
            print("  对比模式: Whisper vs SenseVoice")
            print("🔥" * 35)
            whisper_results = eval_asr(audio_dir, textgrid_dir, args.output_dir, "whisper")
            sensevoice_results = eval_asr(audio_dir, textgrid_dir, args.output_dir, "sensevoice")
            results["asr_whisper"] = whisper_results
            results["asr_sensevoice"] = sensevoice_results

            # 对比汇总
            print("\n" + "=" * 70)
            print("  📊 ASR 引擎对比")
            print("=" * 70)
            print(f"  {'指标':<12} {'Whisper-base':<15} {'SenseVoice':<15} {'提升':<10}")
            print(f"  {'-'*50}")
            w_cer = whisper_results["avg_cer"]
            s_cer = sensevoice_results["avg_cer"]
            w_wer = whisper_results["avg_wer"]
            s_wer = sensevoice_results["avg_wer"]
            cer_diff = w_cer - s_cer
            wer_diff = w_wer - s_wer
            print(f"  {'CER':<12} {w_cer:<15.1%} {s_cer:<15.1%} {'↓'+f'{cer_diff:.1%}':<10}")
            print(f"  {'WER':<12} {w_wer:<15.1%} {s_wer:<15.1%} {'↓'+f'{wer_diff:.1%}':<10}")
        else:
            asr_results = eval_asr(audio_dir, textgrid_dir, args.output_dir, args.engine)
            results["asr"] = asr_results

    # Step 2: RAG 评估
    if not args.asr_only:
        # 构建金标准文档
        documents = build_rag_from_textgrid(textgrid_dir, args.output_dir)

        # 生成 QA 对
        qa_pairs = generate_eval_qa(documents)

        # 保存 QA 对
        os.makedirs(args.output_dir, exist_ok=True)
        qa_path = os.path.join(args.output_dir, "eval_qa_pairs.json")
        with open(qa_path, "w", encoding="utf-8") as f:
            json.dump(qa_pairs, f, ensure_ascii=False, indent=2)
        print(f"\n  💾 QA 对已保存: {qa_path}")

        # 评估 RAG
        rag_results = eval_rag_recall(documents, qa_pairs)
        results["rag"] = rag_results

    # 保存完整结果
    os.makedirs(args.output_dir, exist_ok=True)
    full_path = os.path.join(args.output_dir, "full_eval_results.json")
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 完整评估结果: {full_path}")

    # 最终汇总
    print("\n" + "═" * 70)
    print("  📊 最终评估汇总")
    print("═" * 70)
    if "asr" in results:
        print(f"  ASR 平均 CER:    {results['asr']['avg_cer']:.1%}")
        print(f"  ASR 平均 WER:    {results['asr']['avg_wer']:.1%}")
    if "rag" in results:
        print(f"  RAG Recall@1:    {results['rag']['recall_at_1']:.1%}")
        print(f"  RAG Recall@5:    {results['rag']['recall_at_5']:.1%}")
        print(f"  RAG MRR:         {results['rag']['mrr']:.3f}")
    print("═" * 70)


if __name__ == "__main__":
    main()
