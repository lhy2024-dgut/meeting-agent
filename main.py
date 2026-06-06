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

import config
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
        env = config.ENV_LABELS.get(m.environment, "?")
        ts = m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else ""
        print(f"{m.id:<6} {m.title[:28]:<30} {ts:<20} {dur:<6} {env}")


def cmd_search(args):
    """RAG 检索测试 — 交互式搜索，查看检索结果

    用法: python main.py search [--mode vector|bm25|hybrid] [--no-reranker] [query]
    """
    from rag.retriever import get_retriever, DummyRetriever

    mode, no_reranker, query_parts = _parse_search_args(args)
    print(f"[DEBUG] parsed: mode={mode}, no_reranker={no_reranker}, query_parts={query_parts}")
    try:
        retriever = get_retriever()
    except Exception as e:
        print(f"[ERROR] get_retriever 失败: {e}")
        import traceback; traceback.print_exc()
        return
    print(f"[DEBUG] retriever type: {type(retriever).__name__}")

    if query_parts:
        query = " ".join(query_parts)
        _do_search(retriever, query, mode=mode, enable_reranker=not no_reranker)
        return

    print(f"RAG 检索测试 — mode={mode}, reranker={'off' if no_reranker else 'on'}")
    print("输入问题查看检索结果，输入 /quit 退出\n")
    while True:
        try:
            query = input("Query: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query or query == "/quit":
            break
        _do_search(retriever, query, mode=mode, enable_reranker=not no_reranker)
        print()


def _parse_search_args(args):
    """解析 --mode / --no-reranker 参数，返回 (mode, no_reranker, remaining_args)"""
    mode = None
    no_reranker = False
    remaining = []
    i = 0
    while i < len(args):
        if args[i] == "--mode" and i + 1 < len(args):
            mode = args[i + 1]
            i += 2
        elif args[i] == "--no-reranker":
            no_reranker = True
            i += 1
        else:
            remaining.append(args[i])
            i += 1
    return mode, no_reranker, remaining


def _do_search(retriever, query, top_k=5, mode=None, enable_reranker=None):
    """执行一次检索并格式化输出"""
    kwargs = {"top_k": top_k}
    if mode:
        kwargs["mode"] = mode
    if enable_reranker is not None:
        kwargs["enable_reranker"] = enable_reranker
    try:
        results = retriever.search(query, **kwargs)
    except Exception as e:
        print(f"  ❌ 检索出错: {e}")
        import traceback
        traceback.print_exc()
        return
    results = retriever.enrich_results(results)

    if not results:
        print("  未检索到任何结果")
        return

    print(f"  共检索到 {len(results)} 条结果:\n")
    for i, r in enumerate(results, 1):
        label = r.get("chunk_type_label", r["chunk_type"])
        title = r.get("meeting_title", f"会议#{r['meeting_id']}")
        score = r["score"]
        rerank_score = r.get("rerank_score")
        text = r["text"]

        # 截断显示
        display_text = text[:120] + "..." if len(text) > 120 else text

        if rerank_score is not None:
            print(f"  [{i}] {title} | {label} | rerank={rerank_score:.3f} | score={score:.3f}")
        else:
            print(f"  [{i}] {title} | {label} | 相似度 {score:.3f}")
        print(f"      {display_text}")
        print()


def cmd_eval_rag(args):
    """RAG 检索评估 — 基于内置测试集评估召回率

    用法:
      python main.py eval-rag                           # 用默认模式评估
      python main.py eval-rag --mode hybrid             # 指定模式
      python main.py eval-rag --compare                 # 检索/重排组合对比
      python main.py eval-rag eval_set.json             # 自定义评估集
    """
    from rag.retriever import get_retriever

    # 解析参数
    mode = None
    compare = False
    enable_reranker = None
    eval_file = None
    i = 0
    while i < len(args):
        if args[i] == "--mode" and i + 1 < len(args):
            mode = args[i + 1]
            i += 2
        elif args[i] == "--compare":
            compare = True
            i += 1
        elif args[i] == "--reranker":
            enable_reranker = True
            i += 1
        elif args[i] == "--no-reranker":
            enable_reranker = False
            i += 1
        else:
            eval_file = args[i]
            i += 1

    # 内置评估集
    EVAL_SET = [
        {"query": "会议的主要议题是什么", "keywords": ["议题", "讨论"], "match": "all"},
        {"query": "有哪些待办事项", "keywords": ["待办"], "match": "all"},
        {"query": "会议决议有哪些", "keywords": ["决议"], "match": "all"},
        {"query": "谁负责什么任务", "keywords": ["负责", "跟进"], "match": "any"},
        {"query": "下次会议安排", "keywords": ["下次", "安排"], "match": "all"},
    ]

    if eval_file:
        import json
        try:
            with open(eval_file, "r", encoding="utf-8") as f:
                EVAL_SET = json.load(f)
            print(f"已加载评估集: {eval_file} ({len(EVAL_SET)} 条)")
        except Exception as e:
            print(f"加载评估集失败: {e}")
            return

    retriever = get_retriever()

    if compare:
        # 检索/重排组合对比
        print("\n" + "=" * 60)
        print("  RAG 检索方案对比评估")
        print("=" * 60)
        results_table = {}
        variants = [
            ("vector", "vector", False),
            ("bm25", "bm25", False),
            ("hybrid", "hybrid", False),
            ("hybrid+reranker", "hybrid", True),
        ]
        for label, eval_mode, reranker_flag in variants:
            hit, total, failed = _run_eval(
                retriever,
                EVAL_SET,
                mode=eval_mode,
                enable_reranker=reranker_flag,
            )
            results_table[label] = (hit, total)
            print(f"\n  [{label}] Recall@5: {hit}/{total} = {hit/total:.0%}")
        print("\n" + "=" * 60)
        print("  对比汇总:")
        for m, (hit, total) in results_table.items():
            bar = "█" * int(hit / total * 20) + "░" * (20 - int(hit / total * 20))
            print(f"    {m:<16} {bar} {hit/total:.0%}")
        return

    # 单模式评估
    import config
    effective_mode = mode or getattr(config, "SEARCH_MODE", "vector")
    if enable_reranker is None:
        enable_reranker = getattr(config, "RERANKER_ENABLED", True)
    hit, total, failed = _run_eval(
        retriever,
        EVAL_SET,
        mode=effective_mode,
        enable_reranker=enable_reranker,
    )

    reranker_label = "on" if enable_reranker else "off"
    print(f"\nRAG 检索评估 — {total} 条测试用例 (mode={effective_mode}, reranker={reranker_label})")
    print("=" * 60)
    print(f"  Recall@5: {hit}/{total} = {hit/total:.0%}")

    if hit / total < 0.7:
        print(f"  ⚠️  低于 70%，建议检查 chunk 策略或 embedding 模型")
    elif hit / total < 0.85:
        print(f"  💡 及格，仍有优化空间")
    else:
        print(f"  ✅ 良好")

    if failed:
        print(f"\n失败用例 ({len(failed)} 条):")
        for item in failed:
            print(f"  - '{item['query']}' (期望关键词: {item['keywords']})")


def _run_eval(retriever, eval_set, mode="vector", top_k=5, enable_reranker=False):
    """运行一轮评估，返回 (hit_count, total, failed_list)"""
    hit = 0
    failed = []
    for item in eval_set:
        results = retriever.search(
            item["query"],
            top_k=top_k,
            mode=mode,
            enable_reranker=enable_reranker,
        )
        texts = " ".join(r["text"] for r in results)
        if _eval_hit(texts, item):
            hit += 1
        else:
            failed.append(item)
    return hit, len(eval_set), failed


def _eval_hit(texts, item):
    """根据评估项的匹配规则判断是否命中。"""
    keywords = item.get("keywords", [])
    match = item.get("match", "any")

    if match == "all":
        return all(kw in texts for kw in keywords)
    return any(kw in texts for kw in keywords)


COMMANDS = {
    "transcribe": cmd_transcribe,
    "live": cmd_transcribe_live,
    "minutes": cmd_minutes,
    "export": cmd_export,
    "chat": cmd_chat,
    "history": cmd_history,
    "search": cmd_search,
    "eval-rag": cmd_eval_rag,
}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("可用命令: transcribe | live | minutes | export | chat | history | search | eval-rag")
        print("用法: python main.py <command> [args...]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"未知命令: {cmd}")
        print(f"可用命令: {', '.join(COMMANDS)}")
        sys.exit(1)

    COMMANDS[cmd](sys.argv[2:])
