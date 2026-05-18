# -*- coding: utf-8 -*-
"""上传页"""

from datetime import datetime
from pathlib import Path

import streamlit as st

import config
from db.repository import MeetingRepository
from services.file_service import FileService
from services.meeting_service import MeetingService
from ui.components import error_card, progress_steps


def reset_result():
    for key in ["data", "segments", "output_path", "messages", "pending_question"]:
        st.session_state.pop(key, None)


def page_upload():
    st.header("上传新会议")

    # 上传区
    uploaded = st.file_uploader(
        "拖拽音频或视频文件到此处",
        type=[
            *[e.lstrip(".") for e in config.ALLOWED_AUDIO_EXTENSIONS],
            *[e.lstrip(".") for e in config.ALLOWED_VIDEO_EXTENSIONS],
        ],
        label_visibility="collapsed",
        key="upload_main",
    )

    if uploaded:
        st.audio(uploaded)
        st.markdown('<div style="padding:0.5rem"></div>', unsafe_allow_html=True)

    # 表单卡片
    with st.container(border=True):
        title = st.text_input(
            "会议标题",
            value=uploaded.name.rsplit(".", 1)[0] if uploaded else "",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            meeting_date = st.date_input("日期", value=datetime.now())
        with c2:
            meeting_time = st.time_input("时间", value=datetime.now().time())
        with c3:
            output_format = st.selectbox("导出格式", ["docx", "md", "pdf"], index=0)

        with st.expander("▸ 高级选项", expanded=False):
            tf = st.file_uploader(
                "自定义模板（可选）",
                type=["docx", "md", "pdf"],
                key="tpl",
                label_visibility="collapsed",
            )
            if tf:
                fs = FileService()
                tpl_path, _ = fs.save_uploaded(tf, "template")
                st.session_state.template_path = tpl_path
                st.caption(f"已加载模板：{tf.name}")

        disabled = not uploaded
        cols = st.columns([3, 1])
        with cols[0]:
            clicked = st.button(
                "🚀 开始生成会议纪要",
                type="primary",
                width='stretch',
                disabled=disabled,
                key="btn_generate",
            )
        with cols[1]:
            st.caption("⏱ 预计约 2 分钟")

    if not clicked:
        return

    # ---------- 处理流程 ----------
    reset_result()
    fs = FileService()
    db = MeetingRepository()
    svc = MeetingService(db)

    ext = Path(uploaded.name).suffix.lower()
    file_path, file_hash = fs.save_uploaded(
        uploaded,
        "video" if ext in config.ALLOWED_VIDEO_EXTENSIONS else "audio",
    )
    file_path = fs.prepare_audio_path(file_path, ext)
    meeting_dt = datetime.combine(meeting_date, meeting_time)

    # 进度 UI 区
    st.divider()
    status_text = st.empty()
    progress_bar = st.progress(0)

    steps_placeholder = st.empty()

    def on_progress(pct: int, msg: str):
        progress_bar.progress(min(pct, 100))
        status_text.markdown(f"**{msg}**")
        # 映射到步骤
        if pct < 10:
            step = 0
        elif pct < 55:
            step = 1
        elif pct < 70:
            step = 2
        else:
            step = 3
        with steps_placeholder.container():
            progress_steps(step)

    try:
        result = svc.process(
            file_path,
            file_hash,
            title,
            meeting_dt,
            output_format=output_format,
            template_path=st.session_state.get("template_path"),
            progress_callback=on_progress,
        )
    except Exception as e:
        status_text.empty()
        progress_bar.empty()
        steps_placeholder.empty()
        error_card(
            "处理失败",
            f"错误信息：{str(e)[:200]}。请检查 Ollama 是否运行，或重试。",
            retry_label="🔄 重试",
            retry_key="retry_process",
        )
        return

    progress_bar.progress(100)
    with steps_placeholder.container():
        progress_steps(4)
    status_text.success("✅ 处理完成")

    st.session_state.data = result
    st.session_state.segments = result.get("segments", [])
    st.session_state.output_path = result.get("output_path")
    st.session_state.page = "result"
    st.rerun()
