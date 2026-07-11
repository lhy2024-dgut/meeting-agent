"""
main.py - 主流程入口 
串联：ASR → LLM → 数据库 → 文档导出
命令行用法：python main.py <音频文件路径> [会议标题]
"""

import os
import sys
import shutil
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from modules.asr       import transcribe
from chains.summary_chain import generate_all
from modules.database  import init_db, insert_meeting, insert_transcripts, get_transcripts, insert_summary
from modules.exporter  import export_word, export_markdown, export_pdf

STORAGE_BASE = os.getenv("STORAGE_BASE", "./storage")
AUDIO_DIR    = os.path.join(STORAGE_BASE, "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)


def process(audio_path: str, title: str = None):
    """
    完整流程：
    1. 复制音频到 storage/audio/
    2. ASR 语音识别
    3. LLM 生成4项内容
    4. 存入 PostgreSQL
    5. 导出 Word / Markdown / PDF
    """

    # ── 1. 文件管理：把音频复制到 storage 目录
    filename   = os.path.basename(audio_path)
    saved_path = os.path.join(AUDIO_DIR, filename)
    if os.path.abspath(audio_path) != os.path.abspath(saved_path):
        shutil.copy2(audio_path, saved_path)
    print(f"[文件] 音频已保存至：{saved_path}")

    # ── 2. ASR
    asr_result = transcribe(saved_path)
    transcript = asr_result["text"]
    segments   = asr_result["segments"]

    # ── 3. 初始化数据库 & 存元数据
    init_db()
    meeting_title = title or f"会议_{datetime.now().strftime('%Y%m%d_%H%M')}"
    meeting_id    = insert_meeting(meeting_title, saved_path)
    insert_transcripts(meeting_id, segments, saved_path)
    print(f"[DB] 会议已存储，ID={meeting_id}")

    # ── 4. LLM 生成4项内容
    results = generate_all(transcript)

    # ── 新增：把纪要内容存入 summaries 表
    insert_summary(
    meeting_id=meeting_id,
    summary=results["summary"],
    decisions=results["decisions"],
    todos=results["todos"],
    )
    print(f"[DB] 纪要已存入 summaries 表")

    # ── 5. 导出文档
    doc_data = {
        "title":      meeting_title,
        "date":       datetime.now().strftime("%Y年%m月%d日"),
        "transcript": results["transcript"],
        "summary":    results["summary"],
        "todos":      results["todos"],
        "decisions":  results["decisions"],
    }

    word_path = export_word(doc_data)
    md_path   = export_markdown(doc_data)
    pdf_path  = export_pdf(doc_data)

    print("\n" + "="*50)
    print("✅ 全流程完成！")
    print(f"   会议 ID   : {meeting_id}")
    print(f"   Word 文档 : {word_path}")
    print(f"   Markdown  : {md_path}")
    print(f"   PDF 文档  : {pdf_path}")
    print("="*50)

    return {
        "meeting_id": meeting_id,
        "results":    results,
        "word_path":  word_path,
        "md_path":    md_path,
        "pdf_path":   pdf_path,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python main.py <音频文件路径> [会议标题]")
        print("示例：python main.py D:\\meeting.wav 产品周会")
        sys.exit(1)

    audio  = sys.argv[1]
    title  = sys.argv[2] if len(sys.argv) > 2 else None
    process(audio, title)
