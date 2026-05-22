# -*- coding: utf-8 -*-
"""公共 UI 组件"""

import streamlit as st


def render_header():
    """顶部导航栏"""
    cols = st.columns([3, 1, 1, 1, 1, 1])
    with cols[0]:
        st.markdown(
            '<span style="font-size:20px;font-weight:800;color:#1A1A2E;letter-spacing:-0.02em">'
            "🎙️ Meeting Agent</span>",
            unsafe_allow_html=True,
        )
    nav_pages = [
        ("upload", "📤 上传"),
        ("chat", "💬 问答"),
        ("history", "📚 历史"),
        ("stats", "📊 统计"),
    ]
    for i, (page_key, label) in enumerate(nav_pages, start=1):
        is_active = st.session_state.get("page") == page_key
        color = "#5B5EA6" if is_active else "#64748B"
        weight = "700" if is_active else "500"
        with cols[i]:
            if st.button(
                label,
                key=f"nav_{page_key}",
                width='stretch',
                type="tertiary" if not is_active else "primary",
            ):
                st.session_state.page = page_key
                st.session_state.pop("data", None)
                st.session_state.pop("segments", None)
                st.session_state.pop("output_path", None)
                st.rerun()

    st.markdown(
        '<div style="border-bottom:1px solid #E8ECF0; margin-top:0.5rem; margin-bottom:1.5rem"></div>',
        unsafe_allow_html=True,
    )


def metric_card(label, value, color="#1A1A2E", delta=None):
    """统一指标卡片"""
    with st.container(border=True):
        st.markdown(
            f'<div class="metric-value" style="color:{color}">{value}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="metric-label">{label}</div>', unsafe_allow_html=True)
        if delta:
            st.caption(delta)


def status_pill(text, variant="default"):
    """状态标签

    variant: default | success | warning | danger | info
    """
    colors = {
        "default": ("#F1F5F9", "#475569"),
        "success": ("#D1FAE5", "#059669"),
        "warning": ("#FEF3C7", "#D97706"),
        "danger": ("#FEE2E2", "#DC2626"),
        "info": ("#E0E7FF", "#4F46E5"),
    }
    bg, fg = colors.get(variant, colors["default"])
    return f'<span class="pill" style="background:{bg};color:{fg}">{text}</span>'


def progress_steps(current_step: int):
    """步骤进度指示器

    current_step: 0=ASR, 1=分析分类, 2=LLM提取, 3=导出
    """
    steps = [
        ("🎤", "语音识别"),
        ("📊", "分析分类"),
        ("🤖", "AI 提取"),
        ("📄", "导出文档"),
    ]
    cols = st.columns(len(steps))
    for i, (icon, label) in enumerate(steps):
        with cols[i]:
            if i < current_step:
                bg = "#2D9CDB"
                badge = '<span style="color:#2D9CDB;font-size:12px">✓</span>'
            elif i == current_step:
                bg = "#5B5EA6"
                badge = '<span style="color:#5B5EA6;font-size:12px">⋯</span>'
            else:
                bg = "#E8ECF0"
                badge = ""
            st.markdown(
                f"""
            <div style="text-align:center">
                <div class="step-circle" style="background:{bg};color:white">
                    {icon}
                </div>
                <div class="step-label" style="color:{'#5B5EA6' if i == current_step else '#64748B'}">
                    {label}
                </div>
                {badge}
            </div>
            """,
                unsafe_allow_html=True,
            )


def empty_state(icon, title, description="", action_label=None, action_key=None):
    """空态占位"""
    st.markdown(
        f"""
    <div class="empty-state">
        <div class="empty-icon">{icon}</div>
        <div class="empty-title">{title}</div>
        <div class="empty-desc">{description}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )
    if action_label and action_key:
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button(action_label, key=action_key, type="primary", width='stretch'):
                return True
    return False


def error_card(title, description, retry_label="重试", retry_key="retry"):
    """错误状态卡片"""
    st.markdown(
        f"""
    <div class="error-card">
        <div style="font-size:2.5rem;margin-bottom:0.75rem">⚠️</div>
        <div style="font-size:18px;font-weight:600;color:#DC2626;margin-bottom:0.5rem">{title}</div>
        <div style="font-size:14px;color:#64748B;margin-bottom:1rem">{description}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        return st.button(retry_label, key=retry_key, type="primary", width='stretch')


def suggestion_pills(suggestions, prefix="sg"):
    """建议问题标签组"""
    cols = st.columns(len(suggestions))
    for i, q in enumerate(suggestions):
        with cols[i]:
            if st.button(q, key=f"{prefix}_{i}", width='stretch', type="secondary"):
                return q
    return None
