# -*- coding: utf-8 -*-
"""结果展示页"""

import re
from pathlib import Path

import streamlit as st

import config
from agents.chat_agent import ChatAgent
from chains.export_chain import ExportChain, list_templates
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

    c1, c2, c3, c4 = st.columns([0.6, 2.6, 1.2, 1.2])
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
