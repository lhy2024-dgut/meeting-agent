# -*- coding: utf-8 -*-
"""上传页"""

from datetime import datetime
from pathlib import Path

import streamlit as st

import config
from db.repository import MeetingRepository
from prompts.templates import PromptTemplateLoader
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

        # 场景模板选择（含"自定义模板"选项）
        _CUSTOM_SCENE = "自定义模板"
        scenes = PromptTemplateLoader.list_scenes()
        all_scenes = scenes + [{"scene": _CUSTOM_SCENE, "display_name": "📝 自定义模板", "description": ""}]
        scene_display_names = [s["display_name"] for s in all_scenes]
        selected_scene_idx = st.selectbox(
            "会议场景模板",
            options=range(len(scene_display_names)),
            format_func=lambda i: scene_display_names[i],
            index=0,
            key="scene_selector",
        )
        selected_scene = all_scenes[selected_scene_idx]["scene"]

        # 初始化自定义标题 session state
        if "custom_headings" not in st.session_state:
            st.session_state.custom_headings = []
        if "heading_input_counter" not in st.session_state:
            st.session_state.heading_input_counter = 0

        if selected_scene == _CUSTOM_SCENE:
            # 自定义模板：直接显示标题编辑区，不折叠
            col_input, col_add = st.columns([4, 1])
            with col_input:
                new_heading = st.text_input(
                    "标题",
                    key=f"new_heading_{st.session_state.heading_input_counter}",
                    placeholder="输入标题名称，如：研究进展",
                    label_visibility="collapsed",
                )
            with col_add:
                if st.button("添加", key="btn_add_heading", use_container_width=True):
                    if new_heading.strip():
                        st.session_state.custom_headings.append(new_heading.strip())
                        st.session_state.heading_input_counter += 1
                        st.rerun()

            if st.session_state.custom_headings:
                st.caption("已添加标题：")
                for i, h in enumerate(st.session_state.custom_headings):
                    col_h, col_del = st.columns([6, 1])
                    with col_h:
                        st.markdown(
                            f'<div style="padding:4px 0;font-size:14px">'
                            f"{i + 1}. {h}</div>",
                            unsafe_allow_html=True,
                        )
                    with col_del:
                        if st.button("×", key=f"del_heading_{i}", use_container_width=True):
                            st.session_state.custom_headings.pop(i)
                            st.rerun()
                if st.button("清空全部", key="btn_clear_headings", type="secondary"):
                    st.session_state.custom_headings = []
                    st.rerun()
            else:
                st.caption("⚠️ 请至少添加一个标题，否则无法生成纪要")

        elif selected_scene != PromptTemplateLoader.DEFAULT_SCENE:
            # 内置场景：显示结构预览
            preview = PromptTemplateLoader.get_preview(selected_scene)
            if preview["headings"]:
                headings_str = " → ".join(preview["headings"])
                st.caption(f"📋 默认结构：{headings_str}")
            if preview["description"]:
                st.caption(f"ℹ️ {preview['description']}")

        with st.expander("▸ 高级选项", expanded=False):
            # 术语词表输入
            st.markdown(
                '<div style="font-size:14px;font-weight:600;color:#1E293B;margin-bottom:4px">'
                "📖 术语词表</div>",
                unsafe_allow_html=True,
            )
            st.caption("每行一个词条，填入专有名词可提升 ASR 识别准确率")

            terms_text = st.text_area(
                "词表输入",
                placeholder="分布式系统实验室\n张伟\nProject-X\nDataFlow\n...",
                key="terms_textarea",
                label_visibility="collapsed",
                height=120,
            )

            # Token 估算警告
            if terms_text.strip():
                chinese = sum(1 for c in terms_text if '一' <= c <= '鿿')
                other = len(terms_text) - chinese
                estimated_tokens = int(chinese * 2.0 + other * 0.5)
                if estimated_tokens > 200:
                    st.warning(
                        f"⚠️ 词表约 {estimated_tokens} token，已超过 200 token 限制，"
                        "超出部分将在识别时自动截断"
                    )
                elif estimated_tokens > 50:
                    st.caption(f"💡 词表共估算约 {estimated_tokens} token（上限 200 token）")

            # CSV 导入
            csv_file = st.file_uploader(
                "从 CSV 导入词表",
                type=["csv"],
                key="terms_csv",
                label_visibility="collapsed",
            )
            if csv_file:
                c_csv1, c_csv2 = st.columns([3, 1])
                with c_csv1:
                    st.caption(f"已选择：{csv_file.name}")
                with c_csv2:
                    if st.button("📥 导入并覆盖词表", key="btn_import_csv"):
                        try:
                            content = csv_file.getvalue().decode("utf-8", errors="ignore")
                            lines = [ln.strip() for ln in content.replace("\r\n", "\n").split("\n") if ln.strip()]
                            new_terms = []
                            for line in lines:
                                new_terms.extend([t.strip() for t in line.split(",") if t.strip()])
                            if new_terms:
                                st.session_state.pending_csv_terms = "\n".join(new_terms)
                                st.rerun()
                            else:
                                st.warning("CSV 中未识别到有效词条")
                        except Exception as e:
                            st.warning(f"CSV 解析失败：{e}")

            st.divider()

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

        disabled = not uploaded or (
            selected_scene == _CUSTOM_SCENE and not st.session_state.custom_headings
        )
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

    # 收集场景参数（"自定义模板"在后端等价于通用会议+自定义标题）
    is_custom = selected_scene == "自定义模板"
    scene_to_use = PromptTemplateLoader.DEFAULT_SCENE if is_custom else selected_scene
    custom_headings = st.session_state.get("custom_headings") or None

    # 进度 UI 区
    st.divider()
    status_text = st.empty()
    status_text.markdown("**⏳ 正在加载语音识别模型...**")
    progress_bar = st.progress(0)
    timer_text = st.empty()
    steps_placeholder = st.empty()
    with steps_placeholder.container():
        progress_steps(0)

    def on_progress(pct: int, msg: str):
        progress_bar.progress(min(pct, 100))
        status_text.markdown(f"**{msg}**")
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

    transcript_display = st.empty()
    import time as _time
    asr_wall_start = _time.time()

    # 收集术语词表
    terms_text = st.session_state.get("pending_csv_terms") or st.session_state.get("terms_textarea", "")
    terms_list = [t.strip() for t in terms_text.split("\n") if t.strip()] if terms_text else None

    try:
        result = None
        for event in svc.process_stream(
            file_path,
            file_hash,
            title,
            meeting_dt,
            output_format=output_format,
            template_path=st.session_state.get("template_path"),
            progress_callback=on_progress,
            terms=terms_list,
            scene=scene_to_use,
            custom_headings=custom_headings,
        ):
            if event["type"] == "segment":
                pct = event["progress"]["pct"]
                progress_bar.progress(min(pct, 55))
                status_text.markdown(event["progress"]["msg"])
                elapsed = _time.time() - asr_wall_start
                timer_text.caption(f"⏱ 转写已用时 {elapsed:.0f}s")
                latest = [s["text"] for s in event["progress"]["segments"][-3:]]
                transcript_display.caption(" ".join(latest))
            elif event["type"] == "parallel_progress":
                progress_bar.progress(min(event["pct"], 55))
                status_text.markdown(f"**{event['msg']}**")
                elapsed = _time.time() - asr_wall_start
                timer_text.caption(f"⏱ 转写已用时 {elapsed:.0f}s")
                with steps_placeholder.container():
                    progress_steps(1)
            elif event["type"] == "complete":
                result = event["data"]
    except Exception as e:
        status_text.empty()
        progress_bar.empty()
        timer_text.empty()
        steps_placeholder.empty()
        transcript_display.empty()
        error_card(
            "处理失败",
            f"错误信息：{str(e)[:200]}。请检查 Ollama 是否运行，或重试。",
            retry_label="🔄 重试",
            retry_key="retry_process",
        )
        return

    asr_time = result.get("asr_time", _time.time() - asr_wall_start) if result else 0.0
    transcript_display.empty()
    progress_bar.progress(100)
    with steps_placeholder.container():
        progress_steps(4)
    status_text.success("✅ 处理完成")
    timer_text.caption(f"⏱ 转写耗时 {asr_time:.1f}s")

    st.session_state.data = result
    st.session_state.segments = result.get("segments", [])
    st.session_state.output_path = result.get("output_path")
    st.session_state.page = "result"
    st.rerun()
