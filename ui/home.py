# -*- coding: utf-8 -*-
"""首页"""

import streamlit as st

from db.repository import MeetingRepository
from ui.components import empty_state


def page_home():
    db = MeetingRepository()
    meetings = db.get_all_meetings()

    # Hero
    st.markdown(
        '<div style="padding: 3rem 0 1rem 0">'
        '<div class="hero-title"><span>智能</span>会议纪要助手</div>'
        '<div class="hero-subtitle">'
        "上传会议录音或视频，AI 自动生成纪要、待办事项与决议"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # CTA 双卡片
    col1, col2, col3 = st.columns([0.5, 2.5, 0.5])
    with col2:
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            st.markdown(
                """
            <div class="cta-card">
                <div class="cta-icon">🎤</div>
                <div class="cta-title">上传会议</div>
                <div class="cta-desc">上传音频或视频，AI 自动处理</div>
            </div>
            """,
                unsafe_allow_html=True,
            )
            if st.button("开始处理", key="cta_upload", type="primary", width='stretch'):
                st.session_state.page = "upload"
                st.rerun()
        with c2:
            st.markdown(
                """
            <div class="cta-card">
                <div class="cta-icon">📚</div>
                <div class="cta-title">浏览历史</div>
                <div class="cta-desc">查看过往会议纪要与统计</div>
            </div>
            """,
                unsafe_allow_html=True,
            )
            if st.button("查看历史", key="cta_history", type="secondary", width='stretch'):
                st.session_state.page = "history"
                st.rerun()

    st.markdown('<div style="padding:1.5rem 0"></div>', unsafe_allow_html=True)

    # 统计横条
    if meetings:
        total = len(meetings)
        todos_count = sum(
            len((m.action_items_text or "").split("\n-")) for m in meetings if m.action_items_text
        )
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("已处理会议", f"{total} 场")
            with c2:
                st.metric("待办事项", f"{todos_count} 条")
            with c3:
                st.metric("平均处理", "~4 分钟")
        st.divider()

    # 最近会议
    if meetings:
        st.subheader("最近会议")
        shown = meetings[:3]
        cols = st.columns(len(shown), gap="medium")
        for i, m in enumerate(shown):
            with cols[i]:
                with st.container(border=True):
                    st.markdown(f"**{m.title or '未命名会议'}**")
                    st.caption(
                        f"{m.created_at.strftime('%m-%d · %H:%M') if m.created_at else ''}"
                    )
                    todo_n = (m.action_items_text or "").count("\n-")
                    decision_n = (m.resolutions_text or "").count("\n")
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(
                            f'<span class="pill" style="background:#FEF3C7;color:#D97706">'
                            f"📋 {todo_n} 待办</span>",
                            unsafe_allow_html=True,
                        )
                    with c2:
                        st.markdown(
                            f'<span class="pill" style="background:#DBEAFE;color:#2563EB">'
                            f"🎯 {decision_n} 决议</span>",
                            unsafe_allow_html=True,
                        )
                    if st.button("查看 →", key=f"home_view_{m.id}", width='stretch', type="tertiary"):
                        st.session_state.view_meeting_id = m.id
                        st.session_state.page = "result"
                        st.rerun()
    else:
        empty_state(
            "👋",
            "欢迎使用 Meeting Agent",
            "上传你的第一场会议录音，开始体验 AI 纪要生成",
            action_label="🎤 上传第一场会议",
            action_key="empty_upload",
        )
        if st.session_state.get("empty_upload_clicked"):
            st.session_state.page = "upload"
            st.rerun()
