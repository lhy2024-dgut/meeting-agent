# -*- coding: utf-8 -*-
"""结果展示页"""

import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import config
from agents.chat_agent import ChatAgent
from chains.export_chain import ExportChain, list_templates
from chains.html_summary_chain import HtmlSummaryChain
from chains.minutes_chain import MinutesChain, PLACEHOLDER_ALL_EMPTY
from db.repository import MeetingRepository
from engines.asr_engine import get_asr_engine
from services.terms_service import load_terms, save_terms
from ui.components import empty_state, suggestion_pills


def page_result():
    data = st.session_state.get("data")
    view_id = st.session_state.get("view_meeting_id")

    if view_id and not data:
        db = MeetingRepository()
        meeting = db.get_meeting_by_id(view_id)
        if meeting:
            segments = [
                {"start": item.start_time, "end": item.end_time, "text": item.text}
                for item in meeting.transcriptions
            ]
            data = {
                "meeting_id": meeting.id,
                "title": meeting.title,
                "date": meeting.created_at.strftime("%Y-%m-%d %H:%M") if meeting.created_at else "",
                "minutes": meeting.minutes_text or "",
                "action_items": meeting.action_items_text or "",
                "resolutions": meeting.resolutions_text or "",
                "transcript": " ".join(seg["text"] for seg in segments),
                "segments": segments,
                "duration_category": meeting.duration_category,
                "environment": meeting.environment,
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

    c1, c2, c3, c4, c5 = st.columns([0.6, 2.2, 1.1, 1.0, 1.0])
    with c1:
        if st.button("← 返回", key="back_home", type="tertiary", width="stretch"):
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
        current_fmt = (
            Path(output_path).suffix.lstrip(".")
            if output_path and Path(output_path).exists()
            else None
        )
        export_fmt = st.selectbox(
            "导出格式",
            ["docx", "md", "pdf"],
            index=(
                ["docx", "md", "pdf"].index(current_fmt)
                if current_fmt in ("docx", "md", "pdf")
                else 0
            ),
            key="export_fmt_selector",
            label_visibility="collapsed",
        )
        mime_map = {
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "md": "text/markdown; charset=utf-8",
            "pdf": "application/pdf",
        }
        if output_path and Path(output_path).exists() and Path(output_path).suffix.lstrip(".") == export_fmt:
            path = Path(output_path)
            with open(path, "rb") as file:
                st.download_button(
                    label=f"📥 下载 · {export_fmt}",
                    data=file,
                    file_name=f"meeting_{data.get('meeting_id', 'minutes')}.{export_fmt}",
                    mime=mime_map.get(export_fmt, "application/octet-stream"),
                    width="stretch",
                )
        elif data.get("meeting_id") and data.get("minutes", "").strip():
            if st.button(f"📥 生成 · {export_fmt}", key="btn_export_gen", width="stretch"):
                try:
                    exporter = ExportChain()
                    output_data = {
                        "meeting_id": data.get("meeting_id"),
                        "title": data.get("title", "会议纪要"),
                        "date": data.get("date", ""),
                        "minutes": data.get("minutes", ""),
                        "action_items": data.get("action_items", ""),
                        "resolutions": data.get("resolutions", ""),
                    }
                    st.session_state.output_path = exporter.run(output_data, output_format=export_fmt)
                    st.rerun()
                except Exception as exc:
                    st.error(f"导出失败：{exc}")
    with c4:
        if st.button("🎨 预览样式", key="btn_preview_style", width="stretch"):
            _show_template_preview()
    with c5:
        email_active = st.session_state.get("show_email_panel", False)
        if st.button(
            "✖ 关闭发送" if email_active else "📧 发送邮件",
            key="btn_email_toggle",
            width="stretch",
            type="primary" if email_active else "secondary",
        ):
            st.session_state.show_email_panel = not email_active
            st.rerun()

    st.divider()

    if st.session_state.get("show_email_panel") and data.get("meeting_id"):
        _render_email_panel(data)
        st.divider()

    segments = st.session_state.get("segments", data.get("segments", []))
    if segments:
        duration_sec = max(seg.get("end", 0) for seg in segments)
        duration_min = int(duration_sec // 60)
        duration_text = (
            f"{duration_min} 分钟"
            if duration_min < 60
            else f"{duration_min // 60} 小时 {duration_min % 60} 分"
        )

        env_label = config.ENV_LABELS.get(data.get("environment", ""), "")
        dur_label = config.DURATION_LABELS.get(data.get("duration_category", ""), "")
        asr_time = data.get("asr_time")
        asr_time_text = f"{asr_time:.1f}s" if asr_time else "—"

        cols = st.columns(5)
        with cols[0]:
            with st.container(border=True):
                st.markdown(
                    f'<div style="text-align:center;font-size:22px;font-weight:700;color:#1A1A2E">'
                    f"⏱ {duration_text}</div>"
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
        with cols[4]:
            with st.container(border=True):
                st.markdown(
                    f'<div style="text-align:center;font-size:22px;font-weight:700;color:#3B82F6">'
                    f"🎤 {asr_time_text}</div>"
                    f'<div style="text-align:center;font-size:12px;color:#94A3B8">转写耗时</div>',
                    unsafe_allow_html=True,
                )

    st.markdown('<div style="padding:0.5rem"></div>', unsafe_allow_html=True)

    meeting_id = data.get("meeting_id")
    if meeting_id:
        with st.expander("📖 术语词表（编辑后可重新生成纪要）", expanded=False):
            current_terms = load_terms(meeting_id)
            terms_text = "\n".join(current_terms) if current_terms else ""
            new_terms_text = st.text_area(
                "每行一个词条",
                value=terms_text,
                key="result_terms_edit",
                height=100,
                label_visibility="collapsed",
                placeholder="分布式系统实验室\n张伟\nProject-X\n...",
            )

            col_save, col_regen = st.columns([1, 2])
            with col_save:
                if st.button("💾 保存词表", key="btn_save_terms"):
                    parsed = [term.strip() for term in new_terms_text.strip().split("\n") if term.strip()]
                    save_terms(meeting_id, parsed)
                    st.success("词表已保存")
                    st.rerun()
            with col_regen:
                if st.button(
                    "🔄 保存并重新生成纪要（ASR + LLM）",
                    key="btn_regenerate",
                    type="primary" if current_terms else "secondary",
                ):
                    parsed = [term.strip() for term in new_terms_text.strip().split("\n") if term.strip()]
                    save_terms(meeting_id, parsed)
                    meeting = MeetingRepository().get_meeting_by_id(meeting_id)
                    if not meeting or not meeting.audio_path:
                        st.error("找不到原始音频文件，无法重新生成")
                    else:
                        with st.spinner("🎤 语音识别中..."):
                            asr_engine = get_asr_engine()
                            segments, _ = asr_engine.transcribe(meeting.audio_path, terms=parsed)
                            transcript = " ".join(seg.get("text", "") for seg in segments)
                        with st.spinner("🤖 生成会议纪要中..."):
                            chain = MinutesChain()
                            date_str = (
                                meeting.created_at.strftime("%Y-%m-%d %H:%M")
                                if meeting.created_at
                                else ""
                            )
                            action_items, resolutions, minutes = chain.run(
                                transcript,
                                title=meeting.title,
                                date=date_str,
                            )
                        db = MeetingRepository()
                        db.update_meeting_results(meeting_id, minutes, action_items, resolutions)
                        db.replace_transcriptions(meeting_id, segments)
                        data["minutes"] = minutes
                        data["action_items"] = action_items
                        data["resolutions"] = resolutions
                        data["transcript"] = transcript
                        data["segments"] = segments
                        st.session_state.data = data
                        st.session_state.segments = segments
                        st.session_state.pop("output_path", None)
                        st.session_state.pop("result_agent", None)
                        st.session_state.pop("result_agent_meeting_id", None)
                        st.session_state.result_messages = []
                        st.success("重新生成完成")
                        st.rerun()

    col_left, col_right = st.columns(2, gap="large")

    with col_left:
        with st.container(border=True):
            st.markdown(
                '<div style="font-size:17px;font-weight:700;color:#1E293B;margin-bottom:0.75rem">'
                "📋 待办事项</div>",
                unsafe_allow_html=True,
            )
            action_text = data.get("action_items") or ""
            if action_text.strip() and action_text.strip() not in PLACEHOLDER_ALL_EMPTY:
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
            if resolution_text.strip() and resolution_text.strip() not in PLACEHOLDER_ALL_EMPTY:
                _render_resolutions(resolution_text)
            else:
                st.markdown(
                    '<div style="color:#94A3B8;font-size:14px;padding:1rem 0">'
                    "本次会议未明确决议</div>",
                    unsafe_allow_html=True,
                )

    st.markdown('<div style="padding:0.75rem"></div>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown(
            '<div style="font-size:17px;font-weight:700;color:#1E293B;margin-bottom:0.75rem">'
            "📝 会议纪要</div>",
            unsafe_allow_html=True,
        )
        minutes_text = data.get("minutes") or ""
        if minutes_text.strip() and minutes_text.strip() not in PLACEHOLDER_ALL_EMPTY:
            _render_collapsible_minutes(minutes_text)
        else:
            st.info("纪要内容为空，请检查音频质量或重试。")

    st.markdown('<div style="padding:0.5rem"></div>', unsafe_allow_html=True)

    _render_html_summary_section(data)

    st.markdown('<div style="padding:0.25rem"></div>', unsafe_allow_html=True)

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
                timestamp = seg.get("start", 0)
                minutes = int(timestamp // 60)
                seconds = int(timestamp % 60)
                st.markdown(
                    f'<div class="transcript-line">'
                    f'<span class="transcript-ts">{minutes:02d}:{seconds:02d}</span>'
                    f"{text}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("暂无转录数据")

    st.markdown('<div style="padding:0.75rem"></div>', unsafe_allow_html=True)
    render_chat(data)


def render_chat(data):
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
        meeting_id = data.get("meeting_id")
        if st.session_state.get("result_agent_meeting_id") != meeting_id:
            agent = ChatAgent()
            agent.set_meeting_context(
                data.get("transcript", ""),
                data.get("minutes", ""),
                data.get("action_items", ""),
                data.get("resolutions", ""),
                meeting_id=meeting_id,
            )
            st.session_state.result_agent = agent
            st.session_state.result_agent_meeting_id = meeting_id
            st.session_state.result_messages = []
        agent: ChatAgent = st.session_state.result_agent
    except Exception:
        st.info("问答服务暂不可用")
        return

    stats = agent.get_memory_stats()
    if stats["trimmed"]:
        st.caption("💡 对话已超出 10 轮上限，已自动裁剪最早对话")

    suggested = suggestion_pills(
        ["主要议题是什么？", "有哪些待办事项？", "谁负责哪些任务？"],
        prefix="result_sg",
    )

    if "result_messages" not in st.session_state:
        st.session_state.result_messages = []

    for msg in st.session_state.result_messages:
        bubble_class = "chat-bubble-assistant" if msg["role"] == "assistant" else "chat-bubble-user"
        align = "margin-left: 0;" if msg["role"] == "assistant" else "margin-left: 32px;"
        st.markdown(
            f'<div class="{bubble_class}" style="{align}"><strong>'
            f"{'🤖 助手' if msg['role'] == 'assistant' else '👤 你'}</strong><br>"
            f"{msg['content']}</div>",
            unsafe_allow_html=True,
        )
        rag_hits = msg.get("rag_results", [])
        if rag_hits:
            with st.expander(f"📚 RAG 召回参考（{len(rag_hits)} 条）", expanded=False):
                for index, result in enumerate(rag_hits, 1):
                    score_pct = f"{result.get('score', 0) * 100:.1f}%"
                    title = result.get("meeting_title", "—")
                    label = result.get("chunk_type_label", "—")
                    st.markdown(
                        f'<div style="font-size:12px;color:#6B7280;margin-bottom:2px">'
                        f"**#{index}** [{title}｜{label}]　相似度 **{score_pct}**</div>",
                        unsafe_allow_html=True,
                    )
                    st.caption(result.get("text", "")[:200])

    with st.form("result_chat_form", clear_on_submit=True):
        user_input = st.text_area(
            "输入问题",
            placeholder="基于会议内容提问...（最多500字）",
            label_visibility="collapsed",
            height=68,
            key="result_chat_input",
        )
        char_count = len(user_input) if user_input else 0
        col_info, col_submit = st.columns([5, 1])
        with col_info:
            if char_count > ChatAgent.MAX_USER_INPUT_LEN:
                st.caption(f"⚠️ {char_count}/{ChatAgent.MAX_USER_INPUT_LEN} 已超限")
            elif char_count > 0:
                st.caption(f"{char_count}/{ChatAgent.MAX_USER_INPUT_LEN}")
        with col_submit:
            submitted = st.form_submit_button("发送 →", width="stretch")

    prompt = suggested or (user_input if submitted else None)
    if prompt:
        error = ChatAgent.validate_input(prompt)
        if error:
            st.toast(error, icon="⚠️")
        else:
            st.session_state.result_messages.append({"role": "user", "content": prompt})
            with st.spinner("思考中..."):
                try:
                    response = agent.chat(prompt)
                    rag_results = agent.get_latest_rag_results()
                except Exception:
                    response = "抱歉，LLM 服务暂不可用，请检查 Ollama。"
                    rag_results = []
            st.session_state.result_messages.append(
                {"role": "assistant", "content": response, "rag_results": rag_results}
            )
            st.rerun()


def _show_template_preview():
    templates = list_templates()
    if not templates:
        st.info("暂无可用模板")
        return

    st.markdown(
        '<div style="font-size:18px;font-weight:700;color:#1E293B;margin-bottom:1rem">'
        "🎨 模板预览</div>",
        unsafe_allow_html=True,
    )

    tabs = st.tabs([item["label"] for item in templates])
    for tab, template in zip(tabs, templates):
        with tab:
            if template["preview_path"] and Path(template["preview_path"]).exists():
                st.image(template["preview_path"], use_container_width=True)
            else:
                st.info("暂无预览图")

            supported = []
            if template["has_docx"]:
                supported.append("Word (.docx)")
            if template["has_pdf"]:
                supported.append("PDF")
            st.caption(f"支持格式：{' / '.join(supported)}")


def _render_html_summary_section(data: dict):
    """元宝纪要可视化模块 — 生成 HTML 一图看懂纪要并内嵌展示。"""
    meeting_id = data.get("meeting_id", "")
    minutes_text = data.get("minutes", "")
    if not minutes_text or not minutes_text.strip():
        return

    cache_key = f"html_viz_{meeting_id}"

    with st.container(border=True):
        title_col, btn_col = st.columns([3, 1])
        with title_col:
            st.markdown(
                '<div style="font-size:17px;font-weight:700;color:#1E293B;margin-bottom:0.5rem">'
                "🗂️ 纪要可视化概览</div>",
                unsafe_allow_html=True,
            )
        with btn_col:
            gen_btn = st.button("✨ 生成可视化纪要", key="btn_gen_html", type="primary", use_container_width=True)

        view_mode = st.radio(
            "查看方式",
            options=["显示流程图", "显示代码块"],
            index=0,
            horizontal=True,
            key="html_view_mode",
            label_visibility="collapsed",
        )

        cached_html = st.session_state.get(cache_key)

        if gen_btn:
            with st.spinner("🤖 AI 生成可视化纪要中，请稍候..."):
                try:
                    chain = HtmlSummaryChain()
                    html_out, err = chain.run(data, show_code=False, show_flowchart=True)
                    if err and not html_out:
                        st.error(f"生成失败：{err}")
                        return
                    st.session_state[cache_key] = html_out
                    if err:
                        st.toast(f"生成完成（警告：{err}）", icon="⚠️")
                except Exception as exc:
                    st.error(f"生成异常：{exc}")
                    return
            # 强制重渲，让邮件面板能读到刚写入 session_state 的 viz
            st.rerun()

        if cached_html:
            _render_html_viz(cached_html, data.get("title", "会议纪要"), cache_key, view_mode)
        else:
            st.markdown(
                '<div style="color:#94A3B8;font-size:13px;padding:0.5rem 0">'
                "点击「✨ 生成可视化纪要」，AI 将自动生成可视化会议概览</div>",
                unsafe_allow_html=True,
            )


def _render_html_viz(html: str, title: str, cache_key: str, view_mode: str):
    """渲染 HTML 可视化纪要并提供下载和重新生成按钮。"""
    if view_mode == "显示代码块":
        st.code(html, language="html")
    else:
        estimated_height = min(max(len(html) // 5, 600), 1400)
        components.html(html, height=estimated_height, scrolling=True)

    dl_col, clear_col, _ = st.columns([1, 1, 3])
    with dl_col:
        safe_name = re.sub(r'[\\/*?:"<>|]', "_", title)[:40] or "meeting"
        st.download_button(
            label="📥 下载 HTML",
            data=html.encode("utf-8"),
            file_name=f"{safe_name}_元宝纪要.html",
            mime="text/html; charset=utf-8",
            key=f"dl_html_{cache_key}",
        )
    with clear_col:
        if st.button("🔄 重新生成", key=f"clear_html_{cache_key}", type="tertiary"):
            st.session_state.pop(cache_key, None)
            st.rerun()


_EXPAND_KEY = "minutes_expanded"


def _render_collapsible_minutes(raw_md: str):
    max_preview = 800
    show_full = st.session_state.get(_EXPAND_KEY, False)

    if len(raw_md) > max_preview and not show_full:
        preview = raw_md[:max_preview] + "\n\n> *全文较长，点击下方按钮查看完整内容*"
        st.markdown(
            f'<div class="minutes-paper">{_md_to_html(preview)}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="minutes-paper">{_md_to_html(raw_md)}</div>',
            unsafe_allow_html=True,
        )

    if len(raw_md) > max_preview:
        _, center_col, _ = st.columns([1, 1, 1])
        with center_col:
            label = "📖 收起" if show_full else "📖 展开全文"
            if st.button(label, key="btn_toggle_minutes", type="tertiary", use_container_width=True):
                st.session_state[_EXPAND_KEY] = not show_full
                st.rerun()


def _is_bare_heading(text: str) -> bool:
    if any(text.startswith(prefix) for prefix in ("- ", "• ", "* ", "- [ ] ")):
        return False
    if any(ch in text for ch in ("【", "】", "（", "）", "(", ")")):
        return False
    return len(text) <= 20


def _render_todos(action_text: str):
    for line in action_text.strip().split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            st.markdown(
                f'<div style="font-size:13px;font-weight:600;color:#475569;'
                f'margin:0.6rem 0 0.2rem 0">{stripped[4:]}</div>',
                unsafe_allow_html=True,
            )
            continue
        if stripped.startswith("## "):
            st.markdown(
                f'<div style="font-size:14px;font-weight:700;color:#1E293B;'
                f'margin:0.8rem 0 0.3rem 0;border-bottom:1px solid #E2E8F0;'
                f'padding-bottom:4px">{stripped[3:]}</div>',
                unsafe_allow_html=True,
            )
            continue
        if _is_bare_heading(stripped):
            st.markdown(
                f'<div style="font-size:13px;font-weight:600;color:#475569;'
                f'margin:0.6rem 0 0.2rem 0">{stripped}</div>',
                unsafe_allow_html=True,
            )
            continue
        content = stripped
        for prefix in ("- [ ] ", "- ", "• ", "* "):
            if content.startswith(prefix):
                content = content[len(prefix) :]
                break
        parts = content.split("|")
        desc = parts[0].strip() if parts else content
        meta = " · ".join(part.strip() for part in parts[1:]) if len(parts) > 1 else ""
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
    item_count = 0
    for line in resolution_text.strip().split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            st.markdown(
                f'<div style="font-size:13px;font-weight:600;color:#475569;'
                f'margin:0.6rem 0 0.2rem 0">{stripped[4:]}</div>',
                unsafe_allow_html=True,
            )
            continue
        if stripped.startswith("## "):
            st.markdown(
                f'<div style="font-size:14px;font-weight:700;color:#1E293B;'
                f'margin:0.8rem 0 0.3rem 0;border-bottom:1px solid #E2E8F0;'
                f'padding-bottom:4px">{stripped[3:]}</div>',
                unsafe_allow_html=True,
            )
            continue
        if _is_bare_heading(stripped):
            st.markdown(
                f'<div style="font-size:13px;font-weight:600;color:#475569;'
                f'margin:0.6rem 0 0.2rem 0">{stripped}</div>',
                unsafe_allow_html=True,
            )
            continue
        item_count += 1
        content = re.sub(r"^\d+[\.)、]\s*", "", stripped)
        for prefix in ("- ", "• ", "* "):
            if content.startswith(prefix):
                content = content[len(prefix) :]
                break
        st.markdown(
            f'<div class="decision-item">'
            f'<div class="decision-number">决议 {item_count}</div>'
            f'<div class="decision-text">{content}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )


def _md_to_html(text: str) -> str:
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = re.sub(r"^### (.+)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"^\- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = html.replace("\n\n", "</p><p>").replace("\n", "<br>")
    return f"<p>{html}</p>"


# ─────────────────────────────────────────────────────────────────
# 邮件发送面板
# ─────────────────────────────────────────────────────────────────

def _render_email_panel(data: dict):
    """邮件发送面板：联系人/群组选择 → 附件选项 → 发送 → 结果展示"""
    import os
    import tempfile

    from db.repository import ContactRepository
    from services.email_service import EmailService, _check_smtp_config, build_email_html

    # 配置检查
    ok, cfg_err = _check_smtp_config()

    with st.container(border=True):
        st.markdown(
            '<div style="font-size:16px;font-weight:700;color:#1E293B;margin-bottom:0.75rem">'
            "📧 发送会议纪要邮件</div>",
            unsafe_allow_html=True,
        )

        if not ok:
            st.warning(f"SMTP 未配置：{cfg_err}")
            st.caption(
                "请在项目根目录 .env 文件中设置 SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM"
            )
            return

        db = ContactRepository()
        contacts = db.get_all_contacts()
        groups = db.get_all_groups()

        col_recv, col_att = st.columns([3, 2])

        # ── 收件人 ──
        with col_recv:
            st.markdown("**收件人**")
            recv_mode = st.radio(
                "recv_mode",
                ["按联系人选择", "按群组批量发送"],
                horizontal=True,
                key="email_recv_mode",
                label_visibility="collapsed",
            )

            if recv_mode == "按联系人选择":
                if not contacts:
                    st.info("暂无联系人 — 请先在「联系人」页面添加")
                    return
                sel_cids = st.multiselect(
                    "收件人",
                    options=[c.id for c in contacts],
                    format_func=lambda cid: next(
                        (f"{c.name}  <{c.email}>" for c in contacts if c.id == cid), str(cid)
                    ),
                    key="email_sel_contacts",
                    placeholder="输入姓名或邮箱搜索...",
                    label_visibility="collapsed",
                )
                recipients = [c.email for c in contacts if c.id in sel_cids]
            else:
                if not groups:
                    st.info("暂无群组 — 请先在「联系人」页面创建群组")
                    return
                sel_gids = st.multiselect(
                    "群组",
                    options=[g.id for g in groups],
                    format_func=lambda gid: next(
                        (f"{g.group_name}  ({len(g.contacts)} 人)" for g in groups if g.id == gid), str(gid)
                    ),
                    key="email_sel_groups",
                    placeholder="搜索群组名称...",
                    label_visibility="collapsed",
                )
                # 展开所有群组成员，去重
                recipients = list({
                    c.email
                    for g in groups if g.id in sel_gids
                    for c in g.contacts
                })

            if recipients:
                preview = ", ".join(recipients[:4])
                if len(recipients) > 4:
                    preview += f" 等 {len(recipients)} 人"
                st.caption(f"共 {len(recipients)} 个收件人：{preview}")

        # ── 附件选项 ──
        with col_att:
            st.markdown("**附件**")

            html_cache_key = f"html_viz_{data.get('meeting_id', '')}"
            has_viz_html = bool(st.session_state.get(html_cache_key))
            inc_viz_html = st.checkbox(
                "可视化 HTML 纪要",
                value=has_viz_html,
                disabled=not has_viz_html,
                key="email_inc_viz_html",
                help="需先在结果页点击「✨ 生成可视化纪要」" if not has_viz_html else "将可视化纪要作为 HTML 附件发送",
            )

            output_path = st.session_state.get("output_path") or ""
            _p = Path(output_path) if output_path else None
            cur_fmt = _p.suffix.lstrip(".") if (_p and _p.exists()) else None
            has_minutes = bool(data.get("minutes", "").strip())

            if cur_fmt:
                doc_label = f"文档附件（{cur_fmt.upper()}）"
                doc_help = f"将当前 {cur_fmt} 文件作为附件"
            elif has_minutes:
                doc_label = "文档附件（自动生成 DOCX）"
                doc_help = "发送时自动从纪要内容生成 DOCX 附件"
            else:
                doc_label = "文档附件（无纪要内容）"
                doc_help = "纪要内容为空，无法生成文档"

            inc_doc = st.checkbox(
                doc_label,
                value=bool(cur_fmt or has_minutes),
                disabled=not bool(cur_fmt or has_minutes),
                key="email_inc_doc",
                help=doc_help,
            )

        # ── 邮件主题 ──
        st.markdown("**邮件主题**")
        default_subject = f"【会议纪要】{data.get('title', '会议纪要')}  —  {data.get('date', '')}"
        subject = st.text_input(
            "subject",
            value=default_subject,
            key="email_subject",
            label_visibility="collapsed",
        )

        col_send, col_status = st.columns([1, 3])
        with col_send:
            send_clicked = st.button(
                "📤 发送",
                key="btn_email_send_exec",
                type="primary",
                use_container_width=True,
                disabled=not recipients or not subject.strip(),
            )

        if not send_clicked:
            return

        # ── 执行发送 ──
        minutes = data.get("minutes", "")
        action_items = data.get("action_items", "")
        resolutions = data.get("resolutions", "")
        title = data.get("title", "")
        date_str = data.get("date", "")

        body_text = (
            f"会议纪要：{title}\n日期：{date_str}\n\n"
            f"=== 会议纪要 ===\n{minutes}\n\n"
            f"=== 待办事项 ===\n{action_items}\n\n"
            f"=== 会议决议 ===\n{resolutions}"
        )
        body_html = build_email_html(title, date_str, minutes, action_items, resolutions)

        # 构建附件列表
        attachments = []
        tmp_html_path = None

        if inc_viz_html:
            viz_html = st.session_state.get(html_cache_key, "")
            if viz_html:
                fd, tmp_html_path = tempfile.mkstemp(suffix=".html")
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(viz_html)
                attachments.append(tmp_html_path)

        if inc_doc:
            if cur_fmt and _p and _p.exists():
                attachments.append(str(_p))
            elif has_minutes:
                # 临时生成 DOCX
                try:
                    from chains.export_chain import ExportChain
                    exporter = ExportChain()
                    tmp_doc_path = exporter.run(
                        {
                            "meeting_id": data.get("meeting_id"),
                            "title": data.get("title", "会议纪要"),
                            "date": data.get("date", ""),
                            "minutes": data.get("minutes", ""),
                            "action_items": data.get("action_items", ""),
                            "resolutions": data.get("resolutions", ""),
                        },
                        output_format="docx",
                    )
                    attachments.append(tmp_doc_path)
                    st.session_state.output_path = tmp_doc_path
                except Exception as exc:
                    st.warning(f"文档生成失败，跳过附件：{exc}")

        # 逐个发送
        svc = EmailService()
        db_log = ContactRepository()
        meeting_id = data.get("meeting_id")
        results = []

        progress = st.progress(0, text="准备发送...")
        for idx, addr in enumerate(recipients):
            ok_send, err_msg = svc.send(
                to_email=addr,
                subject=subject.strip(),
                body_text=body_text,
                body_html=body_html,
                attachments=attachments,
            )
            results.append({"email": addr, "success": ok_send, "error": err_msg})
            if meeting_id:
                db_log.add_email_log(
                    meeting_id, addr,
                    "success" if ok_send else "failed",
                    err_msg,
                )
            progress.progress(
                (idx + 1) / len(recipients),
                text=f"已发送 {idx + 1}/{len(recipients)}",
            )

        # 清理临时文件
        if tmp_html_path:
            try:
                os.unlink(tmp_html_path)
            except OSError:
                pass

        # 展示结果
        success_n = sum(1 for r in results if r["success"])
        fail_n = len(results) - success_n

        if fail_n == 0:
            st.success(f"全部发送成功！共 {success_n} 封")
        else:
            st.warning(f"发送完成：{success_n} 成功，{fail_n} 失败")
            with st.expander("查看失败详情", expanded=True):
                for r in results:
                    if not r["success"]:
                        st.error(f"{r['email']}：{r['error']}")
