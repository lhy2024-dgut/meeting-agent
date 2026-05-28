# -*- coding: utf-8 -*-
"""历史会议页 — 分页列表、摘要显示、项目名可编辑"""

import streamlit as st

import config
from db.repository import MeetingRepository
from rag.retriever import get_retriever
from ui.components import empty_state


def page_history():
    st.header("历史会议")

    db = MeetingRepository()

    # 筛选栏
    cols = st.columns([2, 1, 1])
    with cols[0]:
        search = st.text_input(
            "搜索",
            placeholder="搜索标题 / 摘要 / 项目名...",
            label_visibility="collapsed",
            key="history_search",
        )
    with cols[1]:
        dur_filter = st.selectbox(
            "时长",
            ["全部", "短会 (<5min)", "中等 (5-30min)", "长会 (>30min)"],
            label_visibility="collapsed",
            key="history_dur",
        )
    with cols[2]:
        env_filter = st.selectbox(
            "环境",
            ["全部", "安静", "嘈杂", "多人"],
            label_visibility="collapsed",
            key="history_env",
        )

    # 分页
    page_size = 10
    page_key = "history_page"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0
    page = st.session_state[page_key]

    meetings, total = db.get_meetings_paginated(
        page=page,
        page_size=page_size,
        search=search or "",
        dur_filter=dur_filter,
        env_filter=env_filter,
    )

    if total == 0:
        empty_state(
            "📚",
            "暂无会议记录" if not search else "未找到匹配的会议",
            "上传处理第一场会议后，这里会展示所有历史记录" if not search else "请尝试其他筛选条件",
            action_label="🎤 上传会议",
            action_key="history_empty_upload",
        )
        return

    st.caption(f"共 {total} 场会议 · 第 {page + 1}/{max(1, (total + page_size - 1) // page_size)} 页")

    # 会议卡片列表
    for m in meetings:
        with st.container(border=True):
            # 第一行: 标题 + 项目名 + 操作
            c1, c2 = st.columns([3, 1])
            with c1:
                title_col, proj_col = st.columns([2, 1])
                with title_col:
                    st.markdown(f"**{m.title or '未命名会议'}**")
                    ts = m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else ""
                    dur_label = config.DURATION_LABELS.get(m.duration_category, "")
                    env_label = config.ENV_LABELS.get(m.environment, "")
                    st.caption(f"{ts} · {dur_label} · {env_label}")
                with proj_col:
                    _render_project_name(db, m)

                # 摘要
                summary = m.short_summary
                if not summary and m.minutes_text:
                    summary = m.minutes_text[:200].replace("\n", " ")
                if summary:
                    st.markdown(
                        f'<div style="font-size:13px;color:#64748B;line-height:1.5">{summary}</div>',
                        unsafe_allow_html=True,
                    )

                # 统计 pills
                todo_n = (m.action_items_text or "").count("\n-")
                decision_n = (m.resolutions_text or "").count("\n")
                st.markdown(
                    f'<span class="pill" style="background:#FEF3C7;color:#D97706">📋 {todo_n} 待办</span> '
                    f'<span class="pill" style="background:#DBEAFE;color:#2563EB">🎯 {decision_n} 决议</span>',
                    unsafe_allow_html=True,
                )

            with c2:
                st.markdown("<br>", unsafe_allow_html=True)
                col_v, col_d = st.columns(2)
                with col_v:
                    if st.button("📖 查看", key=f"hist_view_{m.id}", use_container_width=True):
                        st.session_state.view_meeting_id = m.id
                        st.session_state.data = None
                        st.session_state.page = "result"
                        st.rerun()
                with col_d:
                    confirm_key = f"hist_del_confirm_{m.id}"
                    if st.session_state.get(confirm_key):
                        if st.button("⚠️ 确认", key=f"hist_del_ok_{m.id}", use_container_width=True, type="primary"):
                            db.delete_meeting(m.id)
                            try:
                                get_retriever().remove_meeting(m.id)
                            except Exception:
                                pass
                            st.session_state[confirm_key] = False
                            st.rerun()
                    else:
                        if st.button("🗑 删除", key=f"hist_del_{m.id}", use_container_width=True, type="secondary"):
                            st.session_state[confirm_key] = True
                            st.rerun()

    # 分页导航
    total_pages = max(1, (total + page_size - 1) // page_size)
    if total_pages > 1:
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button("← 上一页", disabled=page == 0, width='stretch', type="secondary"):
                st.session_state[page_key] = max(0, page - 1)
                st.rerun()
        with col2:
            st.markdown(
                f'<div style="text-align:center;color:#64748B;padding-top:0.5rem">'
                f"{page + 1} / {total_pages}</div>",
                unsafe_allow_html=True,
            )
        with col3:
            if st.button("下一页 →", disabled=page >= total_pages - 1, width='stretch', type="secondary"):
                st.session_state[page_key] = min(total_pages - 1, page + 1)
                st.rerun()


def _render_project_name(db: MeetingRepository, meeting):
    """渲染项目名标签 + 编辑功能"""
    project_name = meeting.project_name or "未分类"

    edit_key = f"hist_edit_proj_{meeting.id}"
    if st.session_state.get(edit_key):
        # 编辑模式
        c1, c2 = st.columns([3, 1])
        with c1:
            new_name = st.text_input(
                "项目名",
                value=project_name if project_name != "未分类" else "",
                placeholder="输入项目名称...",
                label_visibility="collapsed",
                key=f"hist_proj_input_{meeting.id}",
            )
        with c2:
            if st.button("💾", key=f"hist_proj_save_{meeting.id}", use_container_width=True):
                if new_name.strip():
                    db.update_meeting_project_name(meeting.id, new_name.strip())
                st.session_state[edit_key] = False
                st.rerun()
        if st.button("取消", key=f"hist_proj_cancel_{meeting.id}", type="tertiary"):
            st.session_state[edit_key] = False
            st.rerun()
    else:
        # 展示模式
        color = "#6366F1" if project_name != "未分类" else "#94A3B8"
        st.markdown(
            f'<span style="font-size:12px;background:{color}15;color:{color};'
            f'padding:2px 8px;border-radius:10px;cursor:default">'
            f'📁 {project_name}</span>',
            unsafe_allow_html=True,
        )
        if st.button("✏️", key=f"hist_proj_edit_{meeting.id}", type="tertiary"):
            st.session_state[edit_key] = True
            st.rerun()
