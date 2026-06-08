# -*- coding: utf-8 -*-
"""结果展示页"""

import re
from pathlib import Path

import streamlit as st

import config
from agents.chat_agent import ChatAgent
from chains.minutes_chain import MinutesChain
from chains.export_chain import ExportChain, list_templates
from db.repository import MeetingRepository
from engines.asr_engine import ASREngine, _build_initial_prompt
from services.terms_loader import load_terms, save_terms
from ui.components import empty_state, suggestion_pills
from engines.llm import get_llm
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from rag.retriever import get_retriever


def page_result():
    # 支持两种入口：session 中的 data 或 view_meeting_id
    data = st.session_state.get("data")
    view_id = st.session_state.get("view_meeting_id")

    if view_id and not data:
        db = MeetingRepository()
        m = db.get_meeting_by_id(view_id)
        if m:
            segments = [
                {
                    "start": t.start_time,
                    "end": t.end_time,
                    "text": t.text,
                }
                for t in m.transcriptions
            ]
            data = {
                "meeting_id": m.id,
                "title": m.title,
                "date": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "",
                "minutes": m.minutes_text or "",
                "action_items": m.action_items_text or "",
                "resolutions": m.resolutions_text or "",
                "transcript": " ".join(seg["text"] for seg in segments),
                "segments": segments,
                "duration_category": m.duration_category,
                "environment": m.environment,
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

    # ---- 顶部操作栏 ----
    c1, c2, c3, c4 = st.columns([0.6, 2.6, 1.2, 1.2])
    with c1:
        if st.button("← 返回", key="back_home", type="tertiary", width='stretch'):
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
        if output_path and Path(output_path).exists():
            p = Path(output_path)
            with open(p, "rb") as f:
                st.download_button(
                    label=f"📥导出 · {p.suffix.lstrip('.')}",
                    data=f,
                    file_name=f"meeting_{data.get('meeting_id', 'minutes')}{p.suffix}",
                    mime="application/octet-stream",
                    width='stretch',
                )
        elif data.get("meeting_id") and data.get("minutes", "").strip():
            # 历史查看模式：临时生成导出文件
            hist_fmt = st.selectbox("格式", ["docx", "md", "pdf"], key="hist_fmt", label_visibility="collapsed")
            if st.button("📥 导出", key="btn_hist_export", width='stretch'):
                try:
                    ec = ExportChain()
                    output_data = {
                        "meeting_id": data.get("meeting_id"),
                        "title": data.get("title", "会议纪要"),
                        "date": data.get("date", ""),
                        "minutes": data.get("minutes", ""),
                        "action_items": data.get("action_items", ""),
                        "resolutions": data.get("resolutions", ""),
                    }
                    out_path = ec.run(output_data, output_format=hist_fmt)
                    st.session_state.output_path = out_path
                    st.rerun()
                except Exception as e:
                    st.error(f"导出失败：{e}")
    with c4:
        if st.button("🎨 预览样式", key="btn_preview_style", width='stretch'):
            _show_template_preview()

    st.divider()

    # ---- 概览条 ----
    segments = st.session_state.get("segments", data.get("segments", []))
    if segments:
        duration_sec = max(seg.get("end", 0) for seg in segments)
        dur_min = int(duration_sec // 60)
        dur_str = f"{dur_min} 分钟" if dur_min < 60 else f"{dur_min // 60} 小时 {dur_min % 60} 分"

        env_label = config.ENV_LABELS.get(data.get("environment", ""), "")
        dur_label = config.DURATION_LABELS.get(data.get("duration_category", ""), "")

        cols = st.columns(4)
        with cols[0]:
            with st.container(border=True):
                st.markdown(
                    f'<div style="text-align:center;font-size:22px;font-weight:700;color:#1A1A2E">'
                    f"⏱ {dur_str}</div>"
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

    st.markdown('<div style="padding:0.5rem"></div>', unsafe_allow_html=True)

    # ---- 术语词表（可编辑 + 重新生成） ----
    mid = data.get("meeting_id")
    if mid:
        with st.expander("📖 术语词表（编辑后可重新生成纪要）", expanded=False):
            current_terms = load_terms(mid)
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
                    parsed = [t.strip() for t in new_terms_text.strip().split("\n") if t.strip()]
                    save_terms(mid, parsed)
                    st.success("词表已保存")
                    st.rerun()
            with col_regen:
                if st.button(
                    "🔄 保存并重新生成纪要（ASR + LLM）",
                    key="btn_regenerate",
                    type="primary" if current_terms else "secondary",
                ):
                    parsed = [t.strip() for t in new_terms_text.strip().split("\n") if t.strip()]
                    save_terms(mid, parsed)
                    meeting = MeetingRepository().get_meeting_by_id(mid)
                    if not meeting or not meeting.audio_path:
                        st.error("找不到原始音频文件，无法重新生成")
                    else:
                        with st.spinner("🎤 语音识别中..."):
                            asr = ASREngine()
                            prompt = _build_initial_prompt(parsed) if parsed else None
                            segments, duration = asr.transcribe(meeting.audio_path, initial_prompt=prompt)
                            transcript = " ".join(s.get("text", "") for s in segments)
                        with st.spinner("🤖 生成会议纪要中..."):
                            chain = MinutesChain()
                            date_str = (
                                meeting.created_at.strftime("%Y-%m-%d %H:%M")
                                if meeting.created_at else ""
                            )
                            action_items, resolutions, minutes = chain.run(
                                transcript, title=meeting.title, date=date_str
                            )
                        # 更新数据库
                        db = MeetingRepository()
                        db.update_meeting_results(mid, minutes, action_items, resolutions)
                        db.add_transcriptions_bulk(mid, segments)
                        # 更新 session_state
                        data["minutes"] = minutes
                        data["action_items"] = action_items
                        data["resolutions"] = resolutions
                        data["transcript"] = transcript
                        data["segments"] = segments
                        st.session_state.data = data
                        st.success("✅ 重新生成完成")
                        st.rerun()

    # ---- 双栏：待办 + 决议 ----
    col_left, col_right = st.columns(2, gap="large")

    with col_left:
        with st.container(border=True):
            st.markdown(
                '<div style="font-size:17px;font-weight:700;color:#1E293B;margin-bottom:0.75rem">'
                "📋 待办事项</div>",
                unsafe_allow_html=True,
            )
            action_text = data.get("action_items") or ""
            if action_text.strip() and action_text.strip() not in (
                "本次会议未明确待办事项。",
                "请查看会议纪要",
            ):
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
            if resolution_text.strip() and resolution_text.strip() not in (
                "本次会议未明确决议。",
                "请查看会议纪要",
            ):
                _render_resolutions(resolution_text)
            else:
                st.markdown(
                    '<div style="color:#94A3B8;font-size:14px;padding:1rem 0">'
                    "本次会议未明确决议</div>",
                    unsafe_allow_html=True,
                )

    st.markdown('<div style="padding:0.75rem"></div>', unsafe_allow_html=True)

    # ---- 会议纪要 ----
    with st.container(border=True):
        st.markdown(
            '<div style="font-size:17px;font-weight:700;color:#1E293B;margin-bottom:0.75rem">'
            "📝 会议纪要</div>",
            unsafe_allow_html=True,
        )
        minutes_text = data.get("minutes") or ""
        if minutes_text.strip() and minutes_text.strip() != "请查看会议纪要":
            _render_collapsible_minutes(minutes_text)
        else:
            st.info("纪要内容为空，请检查音频质量或重试。")

    st.markdown('<div style="padding:0.5rem"></div>', unsafe_allow_html=True)

    # ---- 转录文本 (折叠) ----
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
                ts = seg.get("start", 0)
                mins = int(ts // 60)
                secs = int(ts % 60)
                st.markdown(
                    f'<div class="transcript-line">'
                    f'<span class="transcript-ts">{mins:02d}:{secs:02d}</span>'
                    f"{text}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("暂无转录数据")

    st.markdown('<div style="padding:0.75rem"></div>', unsafe_allow_html=True)

    # ---- 底部问答 ----
    render_chat(data)


def _stateless_chat(history, meeting_data, new_message):
    """无状态问答：直接用历史消息 + 新问题调 LLM，不依赖 session_state 中的 Agent 实例"""
    # RAG 检索（跨会议知识库）
    try:
        rag_context = get_retriever().build_context(
            new_message,
            top_k=5,
            exclude_meeting_id=meeting_data.get("meeting_id"),
        )
    except Exception:
        rag_context = ""

    ctx = meeting_data
    system_text = (
        f"你正在讨论一场会议，以下为会议相关信息：\n\n"
        f"会议转录摘要：{ctx.get('transcript', '')[:6000]}\n"
        f"会议纪要：{ctx.get('minutes', '')[:2000]}\n"
        f"待办事项：{ctx.get('action_items', '')[:1000]}\n"
        f"会议决议：{ctx.get('resolutions', '')[:1000]}\n\n"
        f"## 知识库检索结果（来自历史会议）\n"
        f"{rag_context or '（暂无历史会议相关知识）'}\n\n"
        f"请基于以上所有信息回答用户问题。优先使用当前会议信息；"
        f"若问题涉及历史会议内容或需要跨会议对比，则使用知识库检索结果。"
        f"要求：准确、简洁、不编造内容。"
    )

    # 构建消息：system prompt + 历史滑窗（最近 10 轮 = 20 条）+ 新问题
    llm_messages = [SystemMessage(content=system_text)]
    for m in history[-20:]:
        if m["role"] == "user":
            llm_messages.append(HumanMessage(content=m["content"]))
        else:
            llm_messages.append(AIMessage(content=m["content"]))
    llm_messages.append(HumanMessage(content=new_message))

    llm = get_llm(temperature=0.7)
    response = llm.invoke(llm_messages)
    return response.content


def render_chat(data):
    """结果页底部会议问答 — 无状态调用，不依赖 session_state 中的 Agent 实例"""
    # 标题行 + 轮次指示
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(
            '<div style="font-size:17px;font-weight:700;color:#1E293B;margin-bottom:0.5rem">'
            "💬 会议问答</div>",
            unsafe_allow_html=True,
        )
    with c2:
        msgs = st.session_state.get("result_messages", [])
        user_rounds = sum(1 for m in msgs if m["role"] == "user")
        is_full = user_rounds >= 10
        round_label = f"第 {user_rounds}/10 轮"
        if is_full:
            round_label += " ⚠️"
        st.markdown(
            f'<span style="font-size:13px;color:#64748B">{round_label}</span>',
            unsafe_allow_html=True,
        )

    mid = data.get("meeting_id")
    if st.session_state.get("result_messages_meeting_id") != mid:
        st.session_state.result_messages = []
        st.session_state.result_messages_meeting_id = mid

    # 超出窗口提示
    msgs = st.session_state.get("result_messages", [])
    if len(msgs) > 20:
        st.caption("💡 对话已超出 10 轮上限，已自动裁剪最早对话")

    # 建议问题
    q = suggestion_pills(
        [
            "主要议题是什么？",
            "有哪些待办事项？",
            "谁负责哪些任务？",
        ],
        prefix="result_sg",
    )

    if "result_messages" not in st.session_state:
        st.session_state.result_messages = []

    # 历史消息
    for msg in st.session_state.result_messages:
        bubble_class = (
            "chat-bubble-assistant" if msg["role"] == "assistant" else "chat-bubble-user"
        )
        align = "margin-left: 0;" if msg["role"] == "assistant" else "margin-left: 32px;"
        st.markdown(
            f'<div class="{bubble_class}" style="{align}"><strong>'
            f"{'🤖 助手' if msg['role'] == 'assistant' else '👤 你'}</strong><br>"
            f"{msg['content']}</div>",
            unsafe_allow_html=True,
        )

    # 输入
    with st.form("result_chat_form", clear_on_submit=True):
        cols = st.columns([5, 1])
        with cols[0]:
            user_input = st.text_input(
                "输入问题",
                placeholder="基于会议内容提问...",
                label_visibility="collapsed",
            )
        with cols[1]:
            submitted = st.form_submit_button("发送 →", width='stretch')

    prompt = q or (user_input if submitted else None)
    if prompt:
        error = ChatAgent.validate_input(prompt)
        if error:
            st.toast(error, icon="⚠️")
        else:
            st.session_state.result_messages.append({"role": "user", "content": prompt})
            with st.spinner("思考中..."):
                try:
                    resp = _stateless_chat(
                        st.session_state.result_messages[:-1],
                        data,
                        prompt,
                    )
                except Exception:
                    resp = "抱歉，LLM 服务暂不可用，请检查 Ollama。"
            st.session_state.result_messages.append({"role": "assistant", "content": resp})
            st.rerun()


# ---- 模板预览 ----

def _show_template_preview():
    """弹出模板预览对话框"""
    templates = list_templates()
    if not templates:
        st.info("暂无可用模板")
        return

    st.markdown(
        '<div style="font-size:18px;font-weight:700;color:#1E293B;margin-bottom:1rem">'
        "🎨 模板预览</div>",
        unsafe_allow_html=True,
    )

    tabs = st.tabs([t["label"] for t in templates])
    for tab, tmpl in zip(tabs, templates):
        with tab:
            if tmpl["preview_path"] and Path(tmpl["preview_path"]).exists():
                st.image(tmpl["preview_path"], use_container_width=True)
            else:
                st.info("暂无预览图")

            sup = []
            if tmpl["has_docx"]:
                sup.append("Word (.docx)")
            if tmpl["has_pdf"]:
                sup.append("PDF")
            st.caption(f"支持格式：{' / '.join(sup)}")


# ---- 辅助函数 ----

_EXPAND_KEY = "minutes_expanded"


def _render_collapsible_minutes(raw_md: str):
    """可折叠的纪要正文：默认显示前 800 字 + 展开全文按钮"""
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
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            label = "📖 收起" if show_full else "📖 展开全文"
            if st.button(label, key="btn_toggle_minutes", type="tertiary", use_container_width=True):
                st.session_state[_EXPAND_KEY] = not show_full
                st.rerun()


def _render_todos(action_text: str):
    lines = action_text.strip().split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # 去掉 markdown 列表前缀
        content = stripped
        for prefix in ("- [ ] ", "- ", "• ", "* "):
            if content.startswith(prefix):
                content = content[len(prefix) :]
                break
        # 尝试拆分 description | person | deadline
        parts = content.split("|")
        desc = parts[0].strip() if parts else content
        meta = " · ".join(p.strip() for p in parts[1:]) if len(parts) > 1 else ""
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
    lines = resolution_text.strip().split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        content = re.sub(r"^\d+[\.\)、]\s*", "", stripped)
        for prefix in ("- ", "• ", "* "):
            if content.startswith(prefix):
                content = content[len(prefix) :]
                break
        st.markdown(
            f'<div class="decision-item">'
            f'<div class="decision-number">决议 {i + 1}</div>'
            f'<div class="decision-text">{content}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )


def _md_to_html(text: str) -> str:
    """简单的 Markdown → HTML 转换（纪要用）"""
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = re.sub(r"^### (.+)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"^\- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = html.replace("\n\n", "</p><p>").replace("\n", "<br>")
    html = f"<p>{html}</p>"
    return html
