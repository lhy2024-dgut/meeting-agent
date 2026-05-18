# -*- coding: utf-8 -*-
"""智能会议纪要 Agent — CLI 入口

用法:
    python main.py transcribe <audio_path>          # 仅语音识别
    python main.py live <audio_path>                # 实时转写（流式输出）
    python main.py minutes <audio_path>             # 生成完整纪要
    python main.py export <meeting_id>              # 重新导出文档
    python main.py chat <meeting_id>                # 交互式会议问答
    python main.py history                          # 查看历史会议列表
"""

import sys
import warnings

# Windows: 将 stdout/stderr 编码切换为 UTF-8，避免中文乱码
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# 屏蔽 LangChain 弃用警告 (RunnableWithMessageHistory → LangGraph)
warnings.filterwarnings("ignore", message=".*RunnableWithMessageHistory.*")

from datetime import datetime
from pathlib import Path

from agents.chat_agent import ChatAgent
from db.repository import MeetingRepository
from engines.asr_engine import ASREngine
from services.meeting_service import MeetingService


def cmd_transcribe(args):
    """语音识别"""
    if len(args) < 1:
        print("用法: python main.py transcribe <audio_path>")
        return
    audio_path = args[0]
    if not Path(audio_path).exists():
        print(f"文件不存在: {audio_path}")
        return

    asr = ASREngine()
    print(f"正在转写: {audio_path}")
    segments, duration = asr.transcribe(audio_path)
    print(f"转写完成，时长 {duration:.1f}s，共 {len(segments)} 个片段\n")
    for seg in segments:
        print(f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}")


def cmd_transcribe_live(args):
    """实时转写（流式输出）"""
    if len(args) < 1:
        print("用法: python main.py live <audio_path>")
        return
    audio_path = args[0]
    if not Path(audio_path).exists():
        print(f"文件不存在: {audio_path}")
        return

    asr = ASREngine()
    print(f"实时转写: {audio_path}\n")
    for item, duration in asr.transcribe_iter(audio_path):
        ts = f"[{item['start']:.1f}s - {item['end']:.1f}s]"
        print(f"{ts} {item['text']}", flush=True)


def cmd_minutes(args):
    """生成会议纪要"""
    if len(args) < 1:
        print("用法: python main.py minutes <audio_path>")
        return
    audio_path = args[0]
    if not Path(audio_path).exists():
        print(f"文件不存在: {audio_path}")
        return

    db = MeetingRepository()
    svc = MeetingService(db)
    file_hash = "cli_" + datetime.now().strftime("%Y%m%d%H%M%S")
    result = svc.process(
        audio_path, file_hash,
        title=Path(audio_path).stem,
        meeting_dt=datetime.now(),
    )
    print("\n=== 待办事项 ===")
    print(result["action_items"])
    print("\n=== 会议决议 ===")
    print(result["resolutions"])
    print("\n=== 会议纪要 ===")
    print(result["minutes"])


def cmd_export(args):
    """导出文档"""
    if len(args) < 1:
        print("用法: python main.py export <meeting_id> [format:docx|md|pdf]")
        return
    meeting_id = int(args[0])
    fmt = args[1] if len(args) > 1 else "docx"

    db = MeetingRepository()
    m = db.get_meeting_by_id(meeting_id)
    if not m:
        print(f"会议不存在: {meeting_id}")
        return

    svc = MeetingService(db)
    data = {
        "meeting_id": m.id,
        "title": m.title,
        "date": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "",
        "minutes": m.minutes_text or "",
        "action_items": m.action_items_text or "",
        "resolutions": m.resolutions_text or "",
    }
    output_path = svc.export(data, output_format=fmt)
    print(f"导出完成: {output_path}")


def cmd_chat(args):
    """会议问答"""
    if len(args) < 1:
        print("用法: python main.py chat <meeting_id>")
        return
    meeting_id = int(args[0])

    db = MeetingRepository()
    m = db.get_meeting_by_id(meeting_id)
    if not m:
        print(f"会议不存在: {meeting_id}")
        return

    transcript = " ".join(t.text for t in m.transcriptions)
    agent = ChatAgent()
    agent.set_meeting_context(
        transcript,
        m.minutes_text or "",
        m.action_items_text or "",
        m.resolutions_text or "",
    )
    print(f"问答模式 — 会议: {m.title}")
    print("输入 /quit 退出\n")

    while True:
        try:
            q = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q == "/quit":
            break
        print(f"Assistant: {agent.chat(q)}\n")


def cmd_history(args):
    """历史会议列表"""
    db = MeetingRepository()
    meetings = db.get_all_meetings()
    if not meetings:
        print("暂无历史记录")
        return
    print(f"{'ID':<6} {'标题':<30} {'创建时间':<20} {'时长':<6} {'环境'}")
    print("-" * 75)
    for m in meetings:
        dur = {"short": "短", "medium": "中", "long": "长"}.get(m.duration_category, "?")
        env = {"quiet": "安静", "noisy": "嘈杂", "multi_speaker": "多人"}.get(m.environment, "?")
        ts = m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else ""
        print(f"{m.id:<6} {m.title[:28]:<30} {ts:<20} {dur:<6} {env}")


COMMANDS = {
    "transcribe": cmd_transcribe,
    "live": cmd_transcribe_live,
    "minutes": cmd_minutes,
    "export": cmd_export,
    "chat": cmd_chat,
    "history": cmd_history,
}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("可用命令: transcribe | live | minutes | export | chat | history")
        print("用法: python main.py <command> [args...]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"未知命令: {cmd}")
        print(f"可用命令: {', '.join(COMMANDS)}")
        sys.exit(1)

    COMMANDS[cmd](sys.argv[2:])
