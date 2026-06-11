# -*- coding: utf-8 -*-
"""独立问答页"""

import streamlit as st

from agents.chat_agent import ChatAgent
from db.repository import MeetingRepository


def page_chat():
    st.header("会议问答")

    db = MeetingRepository()
    meetings = db.get_all_meetings()

    if not meetings:
        st.info("暂无会议记录，请先上传并处理会议音频。")
        if st.button("🎤 上传会议", type="primary"):
            st.session_state.page = "upload"
            st.rerun()
        return

    # 会议选择
    meeting_options = {f"{m.title} ({m.created_at.strftime('%m-%d %H:%M')})": m for m in meetings}
    selected_label = st.selectbox(
        "选择要问答的会议",
        list(meeting_options.keys()),
        label_visibility="collapsed",
    )
    meeting = meeting_options[selected_label]

    # 切换会议时重建 agent 实例
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

    # 上下文信息 + 轮次指示
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            st.markdown(f"**当前会议**：{meeting.title}")
        with c2:
            has_todos = bool(meeting.action_items_text and meeting.action_items_text.strip())
            has_resolutions = bool(meeting.resolutions_text and meeting.resolutions_text.strip())
            st.caption(f"待办: {'有' if has_todos else '无'} · 决议: {'有' if has_resolutions else '无'}")
        with c3:
            stats = agent.get_memory_stats()
            round_text = f"第 {stats['round_count']}/{stats['max_rounds']} 轮"
            if stats["is_full"]:
                round_text += " ⚠️"
            st.markdown(
                f'<span title="对话轮次">{round_text}</span>',
                unsafe_allow_html=True,
            )
            if stats["trimmed"]:
                st.caption("💡 已自动裁剪最早对话")

    # 超出窗口提示
    stats = agent.get_memory_stats()
    if stats["trimmed"]:
        st.toast("💡 对话已达上限，已自动裁剪最早对话，仍可在当前窗口内继续追问", icon="ℹ️")

    # 初始化消息
    if not st.session_state.get("chat_messages"):
        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content": f"您好，我已阅读了「{meeting.title}」的会议内容。您可以问我任何关于本次会议的问题。",
            }
        ]

    # 消息展示
    for msg in st.session_state.chat_messages:
        if msg["role"] == "assistant":
            st.markdown(
                f'<div class="chat-bubble-assistant">'
                f"<strong>🤖 助手</strong><br>"
                f"{msg['content']}"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="chat-bubble-user" style="margin-left:32px">'
                f"<strong>👤 你</strong><br>"
                f"{msg['content']}"
                f"</div>",
                unsafe_allow_html=True,
            )

    # 建议问题
    from ui.components import suggestion_pills

    q = suggestion_pills(
        ["主要议题", "待办事项", "决议内容", "谁负责什么？"],
        prefix="chat_sg",
    )

    # 输入区域
    prompt = st.chat_input("输入你的问题...（最多500字）")

    final_prompt = q or prompt
    if final_prompt:
        # 输入校验
        error = ChatAgent.validate_input(final_prompt)
        if error:
            st.toast(error, icon="⚠️")
        else:
            st.session_state.chat_messages.append({"role": "user", "content": final_prompt})
            with st.spinner("思考中..."):
                try:
                    resp = agent.chat(final_prompt)
                except Exception:
                    resp = "抱歉，LLM 服务暂不可用，请检查 Ollama 是否运行。"
            st.session_state.chat_messages.append({"role": "assistant", "content": resp})
            st.rerun()

    # 底部操作
    _, col2, _ = st.columns([1, 1, 1])
    with col2:
        if st.button("🗑 清空对话", type="tertiary", width='stretch'):
            # 重建 agent 以清空 memory
            transcript = " ".join(t.text for t in meeting.transcriptions)
            new_agent = ChatAgent()
            new_agent.set_meeting_context(
                transcript,
                meeting.minutes_text or "",
                meeting.action_items_text or "",
                meeting.resolutions_text or "",
                meeting_id=meeting.id,
            )
            st.session_state.chat_agent = new_agent
            st.session_state.chat_messages = []
            st.rerun()
