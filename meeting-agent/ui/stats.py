# -*- coding: utf-8 -*-
"""数据统计页"""

import pandas as pd
import plotly.express as px
import streamlit as st

from db.repository import MeetingRepository


def page_stats():
    st.header("数据统计")

    db = MeetingRepository()
    meetings = db.get_all_meetings()

    if not meetings:
        st.info("暂无数据，上传处理会议后这里会展示统计图表。")
        return

    # 指标卡
    total = len(meetings)
    short = sum(1 for m in meetings if m.duration_category == "short")
    medium = sum(1 for m in meetings if m.duration_category == "medium")
    long = sum(1 for m in meetings if m.duration_category == "long")
    multi = sum(1 for m in meetings if m.environment == "multi_speaker")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        with st.container(border=True):
            st.markdown(f'<div class="metric-value">{total}</div>', unsafe_allow_html=True)
            st.markdown('<div class="metric-label">总会议</div>', unsafe_allow_html=True)
    with c2:
        with st.container(border=True):
            st.markdown(f'<div class="metric-value">{short + medium + long}</div>', unsafe_allow_html=True)
            st.markdown('<div class="metric-label">已完成</div>', unsafe_allow_html=True)
    with c3:
        with st.container(border=True):
            st.markdown(f'<div class="metric-value" style="color:#F29E4C">{multi}</div>', unsafe_allow_html=True)
            st.markdown('<div class="metric-label">多人会议</div>', unsafe_allow_html=True)
    with c4:
        with st.container(border=True):
            # 平均时长：从 meetings 里估算
            st.markdown(f'<div class="metric-value">~4m</div>', unsafe_allow_html=True)
            st.markdown('<div class="metric-label">平均处理</div>', unsafe_allow_html=True)

    st.divider()

    # 图表区
    df = pd.DataFrame(
        [
            {
                "时长": {"short": "短会", "medium": "中等", "long": "长会"}.get(m.duration_category, "未知"),
                "环境": {"quiet": "安静", "noisy": "嘈杂", "multi_speaker": "多人"}.get(m.environment, "未知"),
                "日期": m.created_at,
            }
            for m in meetings
        ]
    )

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.subheader("会议时长分布")
        dur_df = df.groupby("时长").size().reset_index(name="数量")
        fig1 = px.bar(
            dur_df,
            x="时长",
            y="数量",
            text="数量",
            color_discrete_sequence=["#5B5EA6"],
        )
        fig1.update_layout(
            height=320,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig1.update_traces(textposition="outside")
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        st.subheader("会议环境分布")
        env_df = df.groupby("环境").size().reset_index(name="数量")
        fig2 = px.pie(
            env_df,
            values="数量",
            names="环境",
            color_discrete_sequence=["#5B5EA6", "#2D9CDB", "#F29E4C"],
        )
        fig2.update_layout(
            height=320,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig2, use_container_width=True)

    # 按时间趋势（有日期数据的）
    if len(df) >= 2:
        st.subheader("会议数量趋势")
        df["月份"] = df["日期"].dt.strftime("%Y-%m")
        trend_df = df.groupby("月份").size().reset_index(name="数量")
        fig3 = px.line(
            trend_df,
            x="月份",
            y="数量",
            markers=True,
            color_discrete_sequence=["#5B5EA6"],
        )
        fig3.update_layout(
            height=280,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig3, use_container_width=True)
