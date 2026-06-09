# -*- coding: utf-8 -*-
"""历史会议页"""

import streamlit as st

import config
from db.repository import MeetingRepository
from rag.retriever import get_retriever
from ui.components import empty_state


def page_history():
    # 清理历史删除确认状态（防止跨页面残留）
    for key in list(st.session_state.keys()):
        if key.startswith("hist_del_confirm_"):
            st.session_state[key] = False

    st.header("历史会议")

    db = MeetingRepository()
    meetings = db.get_all_meetings()

    if not meetings:
        empty_state(
            "📚",
            "暂无会议记录",
            "上传处理第一场会议后，这里会展示所有历史记录",
            action_label="🎤 上传会议",
            action_key="history_empty_upload",
        )
        return

    # 筛选栏
    cols = st.columns([2, 1, 1])
    with cols[0]:
        search = st.text_input(
            "搜索",
            placeholder="搜索会议标题...",
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

    # 过滤
    filtered = []
    for m in meetings:
        if search and search.lower() not in (m.title or "").lower():
            continue
        dur = m.duration_category or ""
        if dur_filter == "短会 (<5min)" and dur != "short":
            continue
        if dur_filter == "中等 (5-30min)" and dur != "medium":
            continue
        if dur_filter == "长会 (>30min)" and dur != "long":
            continue
        env = m.environment or ""
        if env_filter == "安静" and env != "quiet":
            continue
        if env_filter == "嘈杂" and env != "noisy":
            continue
        if env_filter == "多人" and env != "multi_speaker":
            continue
        filtered.append(m)

    st.caption(f"共 {len(filtered)} / {len(meetings)} 场会议")

    if not filtered:
        st.info("未找到匹配的会议，请尝试其他筛选条件")
        return

    # 分页
    page_size = 5
    page_key = "history_page"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0
    total_pages = max(1, (len(filtered) + page_size - 1) // page_size)
    page_start = st.session_state[page_key] * page_size
    page_meetings = filtered[page_start : page_start + page_size]

    # 会议卡片列表
    for m in page_meetings:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{m.title or '未命名会议'}**")
                ts = m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else ""
                dur_label = config.DURATION_LABELS.get(m.duration_category, "")
                env_label = config.ENV_LABELS.get(m.environment, "")
                st.caption(f"{ts} · {dur_label} · {env_label}")

                # 摘要
                if m.minutes_text:
                    preview = m.minutes_text[:150].replace("\n", " ")
                    st.markdown(
                        f'<div style="font-size:13px;color:#64748B;line-height:1.5">{preview}...</div>',
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
    if total_pages > 1:
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button("← 上一页", disabled=st.session_state[page_key] == 0, width='stretch', type="secondary"):
                st.session_state[page_key] = max(0, st.session_state[page_key] - 1)
                st.rerun()
        with col2:
            st.markdown(
                f'<div style="text-align:center;color:#64748B;padding-top:0.5rem">'
                f"{st.session_state[page_key] + 1} / {total_pages}</div>",
                unsafe_allow_html=True,
            )
        with col3:
            if st.button("下一页 →", disabled=st.session_state[page_key] >= total_pages - 1, width='stretch', type="secondary"):
                st.session_state[page_key] = min(total_pages - 1, st.session_state[page_key] + 1)
                st.rerun()
