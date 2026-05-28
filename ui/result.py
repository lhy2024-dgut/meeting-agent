# -*- coding: utf-8 -*-
"""结果展示页"""

import re
from pathlib import Path

import streamlit as st

import config
from agents.chat_agent import ChatAgent
from db.repository import MeetingRepository
from ui.components import empty_state, suggestion_pills


def page_result():
    # 支持两种入口：session 中的 data 或 view_meeting_id
    data = st.session_state.get("data")
    view_id = st.session_state.get("view_meeting_id")

    if view_id and not data:
        db = MeetingRepository()
        m = db.get_meeting_by_id(view_id)
        if m:
            segments = [
                {
                    "start": t.start_time,
                    "end": t.end_time,
                    "text": t.text,
                }
                for t in m.transcriptions
            ]
            data = {
                "meeting_id": m.id,
                "title": m.title,
                "date": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "",
                "minutes": m.minutes_text or "",
                "action_items": m.action_items_text or "",
                "resolutions": m.resolutions_text or "",
                "transcript": " ".join(seg["text"] for seg in segments),
                "segments": segments,
                "duration_category": m.duration_category,
                "environment": m.environment,
            }

    if not data:
        empty_state(
            "📋",
            "暂无会议结果",
            "请先上传并处理会议音频",
            action_label="🎤 上传会议",
            action_key="go_upload_from_result",
        )
        return

    # ---- 顶部操作栏 ----
    c1, c2, c3 = st.columns([0.8, 3, 1])
    with c1:
        if st.button("← 返回", key="back_home", type="tertiary", width='stretch'):
            st.session_state.page = "home"
            st.session_state.pop("view_meeting_id", None)
            st.rerun()
    with c2:
        title = data.get("title", "会议纪要")
        date = data.get("date", "")
        st.markdown(
            f'<div style="font-size:18px;font-weight:700;color:#1E293B">{title}</div>'
            f'<div style="font-size:13px;color:#94A3B8">{date}</div>',
            unsafe_allow_html=True,
        )
    with c3:
        output_path = st.session_state.get("output_path")
        if output_path and Path(output_path).exists():
            p = Path(output_path)
            with open(p, "rb") as f:
                st.download_button(
                    label=f"📥 导出 · {p.suffix.lstrip('.')}",
                    data=f,
                    file_name=f"meeting_{data.get('meeting_id', 'minutes')}{p.suffix}",
                    mime="application/octet-stream",
                    width='stretch',
                )

    st.divider()

    # ---- 概览条 ----
    segments = st.session_state.get("segments", data.get("segments", []))
    if segments:
        duration_sec = max(seg.get("end", 0) for seg in segments)
        dur_min = int(duration_sec // 60)
        dur_str = f"{dur_min} 分钟" if dur_min < 60 else f"{dur_min // 60} 小时 {dur_min % 60} 分"

        env_label = config.ENV_LABELS.get(data.get("environment", ""), "")
        dur_label = config.DURATION_LABELS.get(data.get("duration_category", ""), "")

        cols = st.columns(4)
        with cols[0]:
            with st.container(border=True):
                st.markdown(
                    f'<div style="text-align:center;font-size:22px;font-weight:700;color:#1A1A2E">'
                    f"⏱ {dur_str}</div>"
                    f'<div style="text-align:center;font-size:12px;color:#94A3B8">时长</div>',
                    unsafe_allow_html=True,
                )
        with cols[1]:
            with st.container(border=True):
                st.markdown(
                    f'<div style="text-align:center;font-size:22px;font-weight:700;color:#1A1A2E">'
                    f"👥 {env_label}</div>"
                    f'<div style="text-align:center;font-size:12px;color:#94A3B8">会议类型</div>',
                    unsafe_allow_html=True,
                )
        with cols[2]:
            with st.container(border=True):
                st.markdown(
                    f'<div style="text-align:center;font-size:22px;font-weight:700;color:#1A1A2E">'
                    f"📋 {dur_label}</div>"
                    f'<div style="text-align:center;font-size:12px;color:#94A3B8">时长分类</div>',
                    unsafe_allow_html=True,
                )
        with cols[3]:
            action_count = (data.get("action_items") or "").count("\n-")
            with st.container(border=True):
                st.markdown(
                    f'<div style="text-align:center;font-size:22px;font-weight:700;color:#F29E4C">'
                    f"{action_count}</div>"
                    f'<div style="text-align:center;font-size:12px;color:#94A3B8">待办事项</div>',
                    unsafe_allow_html=True,
                )

    st.markdown('<div style="padding:0.5rem"></div>', unsafe_allow_html=True)

    # ---- 双栏：待办 + 决议 ----
    col_left, col_right = st.columns(2, gap="large")

    with col_left:
        with st.container(border=True):
            st.markdown(
                '<div style="font-size:17px;font-weight:700;color:#1E293B;margin-bottom:0.75rem">'
                "📋 待办事项</div>",
                unsafe_allow_html=True,
            )
            action_text = data.get("action_items") or ""
            if action_text.strip() and action_text.strip() not in (
                "本次会议未明确待办事项。",
                "请查看会议纪要",
            ):
                _render_todos(action_text)
            else:
                st.markdown(
                    '<div style="color:#94A3B8;font-size:14px;padding:1rem 0">'
                    "本次会议未明确待办事项</div>",
                    unsafe_allow_html=True,
                )

    with col_right:
        with st.container(border=True):
            st.markdown(
                '<div style="font-size:17px;font-weight:700;color:#1E293B;margin-bottom:0.75rem">'
                "🎯 会议决议</div>",
                unsafe_allow_html=True,
            )
            resolution_text = data.get("resolutions") or ""
            if resolution_text.strip() and resolution_text.strip() not in (
                "本次会议未明确决议。",
                "请查看会议纪要",
            ):
                _render_resolutions(resolution_text)
            else:
                st.markdown(
                    '<div style="color:#94A3B8;font-size:14px;padding:1rem 0">'
                    "本次会议未明确决议</div>",
                    unsafe_allow_html=True,
                )

    st.markdown('<div style="padding:0.75rem"></div>', unsafe_allow_html=True)

    # ---- 会议纪要 ----
    with st.container(border=True):
        st.markdown(
            '<div style="font-size:17px;font-weight:700;color:#1E293B;margin-bottom:0.75rem">'
            "📝 会议纪要</div>",
            unsafe_allow_html=True,
        )
        minutes_text = data.get("minutes") or ""
        if minutes_text.strip() and minutes_text.strip() != "请查看会议纪要":
            st.markdown(
                f'<div class="minutes-paper">{_md_to_html(minutes_text)}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("纪要内容为空，请检查音频质量或重试。")

    st.markdown('<div style="padding:0.5rem"></div>', unsafe_allow_html=True)

    # ---- 转录文本 (折叠) ----
    with st.expander("📜 查看原始转录文本", expanded=False):
        transcripts = segments or data.get("segments", [])
        if transcripts:
            search = st.text_input(
                "搜索转录内容",
                placeholder="输入关键词过滤...",
                key="transcript_search",
                label_visibility="collapsed",
            )
            for seg in transcripts:
                text = seg.get("text", "")
                if search and search.lower() not in text.lower():
                    continue
                ts = seg.get("start", 0)
                mins = int(ts // 60)
                secs = int(ts % 60)
                st.markdown(
                    f'<div class="transcript-line">'
                    f'<span class="transcript-ts">{mins:02d}:{secs:02d}</span>'
                    f"{text}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("暂无转录数据")

    st.markdown('<div style="padding:0.75rem"></div>', unsafe_allow_html=True)

    # ---- 底部问答 ----
    render_chat(data)


def render_chat(data):
    """结果页底部会议问答 — 含 LangGraph Memory 轮次显示"""
    # 标题行 + 轮次指示
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(
            '<div style="font-size:17px;font-weight:700;color:#1E293B;margin-bottom:0.5rem">'
            "💬 会议问答</div>",
            unsafe_allow_html=True,
        )
    with c2:
        try:
            agent_check = st.session_state.get("result_agent")
            if agent_check:
                stats = agent_check.get_memory_stats()
                round_label = f"第 {stats['round_count']}/{stats['max_rounds']} 轮"
                if stats["is_full"]:
                    round_label += " ⚠️"
                st.markdown(
                    f'<span style="font-size:13px;color:#64748B">{round_label}</span>',
                    unsafe_allow_html=True,
                )
        except Exception:
            pass

    try:
        mid = data.get("meeting_id")
        if st.session_state.get("result_agent_meeting_id") != mid:
            agent = ChatAgent()
            agent.set_meeting_context(
                data.get("transcript", ""),
                data.get("minutes", ""),
                data.get("action_items", ""),
                data.get("resolutions", ""),
                meeting_id=mid,
            )
            st.session_state.result_agent = agent
            st.session_state.result_agent_meeting_id = mid
            st.session_state.result_messages = []
        agent: ChatAgent = st.session_state.result_agent
    except Exception:
        st.info("问答服务暂不可用")
        return

    # 超出窗口提示
    stats = agent.get_memory_stats()
    if stats["trimmed"]:
        st.caption("💡 对话已超出 10 轮上限，已自动裁剪最早对话")

    # 建议问题
    q = suggestion_pills(
        [
            "主要议题是什么？",
            "有哪些待办事项？",
            "谁负责哪些任务？",
        ],
        prefix="result_sg",
    )

    if "result_messages" not in st.session_state:
        st.session_state.result_messages = []

    # 历史消息
    for msg in st.session_state.result_messages:
        bubble_class = (
            "chat-bubble-assistant" if msg["role"] == "assistant" else "chat-bubble-user"
        )
        align = "margin-left: 0;" if msg["role"] == "assistant" else "margin-left: 32px;"
        st.markdown(
            f'<div class="{bubble_class}" style="{align}"><strong>'
            f"{'🤖 助手' if msg['role'] == 'assistant' else '👤 你'}</strong><br>"
            f"{msg['content']}</div>",
            unsafe_allow_html=True,
        )

    # 输入
    with st.form("result_chat_form", clear_on_submit=True):
        user_input = st.text_area(
            "输入问题",
            placeholder="基于会议内容提问...（最多500字）",
            label_visibility="collapsed",
            height=68,
            key="result_chat_input",
        )
        n_chars = len(user_input) if user_input else 0
        c1, c2 = st.columns([5, 1])
        with c1:
            if n_chars > ChatAgent.MAX_USER_INPUT_LEN:
                st.caption(f"⚠️ {n_chars}/{ChatAgent.MAX_USER_INPUT_LEN} 已超限")
            elif n_chars > 0:
                st.caption(f"{n_chars}/{ChatAgent.MAX_USER_INPUT_LEN}")
        with c2:
            submitted = st.form_submit_button("发送 →", width='stretch')

    prompt = q or (user_input if submitted else None)
    if prompt:
        error = ChatAgent.validate_input(prompt)
        if error:
            st.toast(error, icon="⚠️")
        else:
            st.session_state.result_messages.append({"role": "user", "content": prompt})
            with st.spinner("思考中..."):
                try:
                    resp = agent.chat(prompt)
                except Exception:
                    resp = "抱歉，LLM 服务暂不可用，请检查 Ollama。"
            st.session_state.result_messages.append({"role": "assistant", "content": resp})
            st.rerun()


# ---- 辅助函数 ----

def _render_todos(action_text: str):
    lines = action_text.strip().split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # 去掉 markdown 列表前缀
        content = stripped
        for prefix in ("- [ ] ", "- ", "• ", "* "):
            if content.startswith(prefix):
                content = content[len(prefix) :]
                break
        # 尝试拆分 description | person | deadline
        parts = content.split("|")
        desc = parts[0].strip() if parts else content
        meta = " · ".join(p.strip() for p in parts[1:]) if len(parts) > 1 else ""
        st.markdown(
            f'<div class="todo-item">'
            f'<div class="todo-dot"></div>'
            f'<div class="todo-content">'
            f'<div class="todo-text">{desc}</div>'
            f'<div class="todo-meta">{meta}</div>'
            f"</div></div>",
            unsafe_allow_html=True,
        )


def _render_resolutions(resolution_text: str):
    lines = resolution_text.strip().split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        content = re.sub(r"^\d+[\.\)、]\s*", "", stripped)
        for prefix in ("- ", "• ", "* "):
            if content.startswith(prefix):
                content = content[len(prefix) :]
                break
        st.markdown(
            f'<div class="decision-item">'
            f'<div class="decision-number">决议 {i + 1}</div>'
            f'<div class="decision-text">{content}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )


def _md_to_html(text: str) -> str:
    """简单的 Markdown → HTML 转换（纪要用）"""
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = re.sub(r"^### (.+)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"^\- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = html.replace("\n\n", "</p><p>").replace("\n", "<br>")
    html = f"<p>{html}</p>"
    return html
