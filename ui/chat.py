# -*- coding: utf-8 -*-
"""独立问答页 — 单场会议问答 / 跨会议检索"""

import streamlit as st

from agents.chat_agent import ChatAgent
from db.repository import MeetingRepository


def page_chat():
    st.header("会议问答")

    db = MeetingRepository()
    meetings = db.get_all_meetings()

    # 模式切换
    mode = st.radio(
        "检索范围",
        ["单场会议问答", "跨会议检索"],
        horizontal=True,
        key="chat_mode",
        help=(
            "单场会议问答：聚焦某一场会议，深度解读该会议的内容\n\n"
            "跨会议检索：从所有会议知识库中关联检索，回答时注明来源会议"
        ),
    )

    st.divider()

    if mode == "单场会议问答":
        _single_meeting_chat(meetings)
    else:
        _cross_meeting_chat(meetings)


# ─────────────────────────────────────────────────────────────────
# 单场会议问答
# ─────────────────────────────────────────────────────────────────

def _single_meeting_chat(meetings):
    if not meetings:
        st.info("暂无会议记录，请先上传并处理会议音频。")
        if st.button("上传会议", type="primary"):
            st.session_state.page = "upload"
            st.rerun()
        return

    # 会议选择 — selectbox 原生支持输入过滤 + 展开下拉两种交互方式
    labels = [
        f"{m.title}    {m.created_at.strftime('%m-%d %H:%M')}"
        for m in meetings
    ]
    sel = st.selectbox(
        "选择会议",
        range(len(meetings)),
        format_func=lambda i: labels[i],
        key="single_mtg_sel",
        label_visibility="collapsed",
        placeholder="输入名称搜索，或点击右侧下拉选择...",
    )
    meeting = meetings[sel]

    # 切换会议时重建 agent
    if st.session_state.get("agent_meeting_id") != meeting.id:
        transcript = " ".join(t.text for t in meeting.transcriptions)
        agent = ChatAgent()
        agent.set_meeting_context(
            transcript,
            meeting.minutes_text or "",
            meeting.action_items_text or "",
            meeting.resolutions_text or "",
            meeting_id=meeting.id,
        )
        st.session_state.chat_agent = agent
        st.session_state.agent_meeting_id = meeting.id
        st.session_state.chat_messages = []

    agent: ChatAgent = st.session_state.chat_agent
    stats = agent.get_memory_stats()

    # 信息条
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 2, 2])
        with c1:
            st.markdown(f"**{meeting.title}**")
            if meeting.short_summary:
                st.caption(meeting.short_summary[:60])
        with c2:
            has_todos = bool(meeting.action_items_text and meeting.action_items_text.strip())
            has_res = bool(meeting.resolutions_text and meeting.resolutions_text.strip())
            st.caption(f"待办: {'有' if has_todos else '无'}   决议: {'有' if has_res else '无'}")
        with c3:
            round_text = f"第 {stats['round_count']}/{stats['max_rounds']} 轮"
            if stats["is_full"]:
                round_text += "  !"
            st.caption(round_text)

    if stats["trimmed"]:
        st.toast("对话已达上限，已自动裁剪最早对话", icon="i")

    # 初始消息
    if not st.session_state.get("chat_messages"):
        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content": f"您好，我已阅读了「{meeting.title}」的会议内容，请随时提问。",
            }
        ]

    _render_messages(st.session_state.chat_messages, show_rag=True)
    _chat_input(agent, "chat_sg", "chat_messages")

    _, col2, _ = st.columns([1, 1, 1])
    with col2:
        if st.button("清空对话", type="tertiary", width="stretch", key="clear_single"):
            transcript = " ".join(t.text for t in meeting.transcriptions)
            a = ChatAgent()
            a.set_meeting_context(
                transcript,
                meeting.minutes_text or "",
                meeting.action_items_text or "",
                meeting.resolutions_text or "",
                meeting_id=meeting.id,
            )
            st.session_state.chat_agent = a
            st.session_state.chat_messages = []
            st.rerun()


# ─────────────────────────────────────────────────────────────────
# 跨会议检索
# ─────────────────────────────────────────────────────────────────

def _cross_meeting_chat(meetings):
    n = len(meetings)

    if not n:
        st.info("暂无会议记录，请先上传并处理会议音频。")
        return

    st.caption(f"跨会议检索 — 从 {n} 场会议知识库中关联检索，回答时将注明来源会议")

    # 跨会议 agent
    if st.session_state.get("chat_agent_cross") is None:
        agent = ChatAgent()
        agent.set_meeting_context(cross_meeting=True)
        st.session_state.chat_agent_cross = agent
        st.session_state.chat_messages_cross = []

    agent: ChatAgent = st.session_state.chat_agent_cross
    stats = agent.get_memory_stats()

    round_text = f"对话轮次：{stats['round_count']}/{stats['max_rounds']}"
    if stats["is_full"]:
        round_text += "  !"
        st.toast("对话已达上限，已自动裁剪最早对话", icon="i")
    st.caption(round_text)

    # 初始消息
    if not st.session_state.get("chat_messages_cross"):
        st.session_state.chat_messages_cross = [
            {
                "role": "assistant",
                "content": (
                    f"您好，我可以从 {n} 场历史会议中检索相关信息来回答您的问题，"
                    "回答时会注明内容来自哪场会议。"
                ),
            }
        ]

    _render_messages(st.session_state.chat_messages_cross, show_rag=True, cross_mode=True)
    _chat_input(agent, "chat_cross_sg", "chat_messages_cross")

    _, col2, _ = st.columns([1, 1, 1])
    with col2:
        if st.button("清空对话", type="tertiary", width="stretch", key="clear_cross"):
            a = ChatAgent()
            a.set_meeting_context(cross_meeting=True)
            st.session_state.chat_agent_cross = a
            st.session_state.chat_messages_cross = []
            st.rerun()


# ─────────────────────────────────────────────────────────────────
# 共用组件
# ─────────────────────────────────────────────────────────────────

def _render_messages(messages, show_rag=False, cross_mode=False):
    for msg in messages:
        if msg["role"] == "assistant":
            st.markdown(
                '<div class="chat-bubble-assistant">'
                "<strong>助手</strong><br>"
                f"{msg['content']}"
                "</div>",
                unsafe_allow_html=True,
            )
            if show_rag:
                _render_rag_hits(msg.get("rag_results", []), cross_mode=cross_mode)
        else:
            st.markdown(
                '<div class="chat-bubble-user" style="margin-left:32px">'
                "<strong>你</strong><br>"
                f"{msg['content']}"
                "</div>",
                unsafe_allow_html=True,
            )


def _render_rag_hits(rag_hits, cross_mode=False):
    if not rag_hits:
        return
    meeting_titles = list(dict.fromkeys(
        r.get("meeting_title", "") for r in rag_hits if r.get("meeting_title")
    ))
    label = f"RAG 召回 — {len(rag_hits)} 条"
    if cross_mode and meeting_titles:
        label += f" / 来自 {len(meeting_titles)} 场会议"
    with st.expander(f"📚 {label}", expanded=False):
        for i, r in enumerate(rag_hits, 1):
            score_pct = f"{r.get('score', 0) * 100:.1f}%"
            title = r.get("meeting_title", "—")
            label_type = r.get("chunk_type_label", "—")
            st.markdown(
                f'<div style="font-size:12px;color:#6B7280;margin-bottom:2px">'
                f"<b>#{i}</b> 《{title}》 {label_type}   相似度 <b>{score_pct}</b></div>",
                unsafe_allow_html=True,
            )
            if cross_mode:
                summary = r.get("meeting_summary", "")
                if summary:
                    st.caption(f"摘要：{summary[:80]}")
            st.caption(r.get("text", "")[:200])
            if i < len(rag_hits):
                st.markdown(
                    '<hr style="margin:4px 0;border-color:#E2E8F0">',
                    unsafe_allow_html=True,
                )


def _chat_input(agent: ChatAgent, sg_prefix: str, msg_key: str):
    from ui.components import suggestion_pills

    q = suggestion_pills(
        ["主要议题", "待办事项", "决议内容", "谁负责什么"],
        prefix=sg_prefix,
    )
    prompt = st.chat_input("输入问题...（最多 500 字）")
    final = q or prompt
    if not final:
        return

    err = ChatAgent.validate_input(final)
    if err:
        st.toast(err, icon="warning")
        return

    msgs = st.session_state[msg_key]
    msgs.append({"role": "user", "content": final})

    with st.spinner("思考中..."):
        try:
            resp = agent.chat(final)
            rag_results = agent.get_latest_rag_results()
        except Exception:
            resp = "抱歉，LLM 服务暂不可用，请检查 Ollama 是否运行。"
            rag_results = []

    msgs.append({"role": "assistant", "content": resp, "rag_results": rag_results})
    st.rerun()
