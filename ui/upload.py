# -*- coding: utf-8 -*-
"""上传页"""

import difflib
import html
import re
import time as _time
from datetime import datetime
from pathlib import Path

import streamlit as st

import config
from db.repository import MeetingRepository
from prompts.templates import PromptTemplateLoader
from services.file_service import FileService
from services.meeting_service import MeetingService, ASR_MODEL_WHISPER, ASR_MODEL_SENSEVOICE
from config import CHUNK_STRATEGY_FIXED, CHUNK_STRATEGY_SEGMENT, CHUNK_STRATEGY_SEMANTIC
from services.terms_service import truncate_terms, _estimate_tokens
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

    # ── 文件一旦上传，立即保存到磁盘并记入 session_state ──────────────────
    # 这样后续 rerun（如用户在 expander 内输入文本）不会因 uploaded 变 None 而
    # 导致按钮误判为 disabled 或处理流中出现 NoneType 错误。
    if uploaded is not None:
        _saved_name = st.session_state.get("_saved_file_name")
        if _saved_name != uploaded.name:
            _fs_early = FileService()
            _ext_early = Path(uploaded.name).suffix.lower()
            _saved_path, _saved_hash = _fs_early.save_uploaded(
                uploaded,
                "video" if _ext_early in config.ALLOWED_VIDEO_EXTENSIONS else "audio",
            )
            st.session_state["_saved_file_path"] = _saved_path
            st.session_state["_saved_file_hash"] = _saved_hash
            st.session_state["_saved_file_ext"] = _ext_early
            st.session_state["_saved_file_name"] = uploaded.name
    else:
        # 用户清除了文件 → 同步清除 session_state 里的缓存路径
        for _k in ["_saved_file_path", "_saved_file_hash", "_saved_file_ext", "_saved_file_name"]:
            st.session_state.pop(_k, None)

    _has_file = st.session_state.get("_saved_file_path") is not None

    if uploaded:
        st.audio(uploaded)
        st.markdown('<div style="padding:0.5rem"></div>', unsafe_allow_html=True)

    # 表单卡片
    with st.container(border=True):
        title = st.text_input(
            "会议标题",
            value=st.session_state.get("_saved_file_name", "").rsplit(".", 1)[0],
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

        st.divider()

        # ── ASR 模型选择 ──────────────────────────────────────────────────────
        asr_model = st.radio(
            "语音识别模型",
            options=[ASR_MODEL_WHISPER, ASR_MODEL_SENSEVOICE],
            index=0,
            horizontal=True,
            help=(
                "**faster-whisper**：OpenAI Whisper 加速版，支持 initial_prompt 术语注入\n\n"
                "**SenseVoiceSmall**：FunAudioLLM 开源模型，内置 VAD，支持 hotword 术语注入"
            ),
        )

        # ── Chunk 切分策略选择 ────────────────────────────────────────────────
        _CHUNK_OPTIONS = {
            CHUNK_STRATEGY_FIXED:    "固定 512 字",
            CHUNK_STRATEGY_SEGMENT:  "按句子合并 300 字",
            CHUNK_STRATEGY_SEMANTIC: "语义切分",
        }
        _CHUNK_HELP = {
            CHUNK_STRATEGY_FIXED:
                "按字符数递归切分，512 字一块，64 字重叠。速度最快，适合大多数场景。",
            CHUNK_STRATEGY_SEGMENT:
                "将 ASR 输出的 segment 逐句合并至约 300 字，天然语义完整，自带时间戳。"
                "需配合所选 ASR 模型使用（faster-whisper / SenseVoiceSmall 各有独立实现）。",
            CHUNK_STRATEGY_SEMANTIC:
                "用 bge-m3 计算相邻句子余弦相似度，在话题切换处（相似度断崖）切块。"
                "chunk 语义最连贯，但需额外 embedding 计算，速度稍慢。",
        }
        chunk_strategy_label = st.radio(
            "RAG 切分策略",
            options=list(_CHUNK_OPTIONS.keys()),
            format_func=lambda k: _CHUNK_OPTIONS[k],
            index=0,
            horizontal=True,
            key="chunk_strategy_selector",
        )
        st.caption(f"ℹ️ {_CHUNK_HELP[chunk_strategy_label]}")

        # ── 转写策略选择 ──────────────────────────────────────────────────────
        transcription_mode = st.radio(
            "转写策略",
            options=["auto", "direct", "parallel"],
            format_func=lambda m: {"auto": "自动（按时长）", "direct": "直接转写", "parallel": "并行转写"}[m],
            index=0,
            horizontal=True,
            help=(
                "**自动**：音频 <90s 直接转写，≥90s 自动切换并行\n\n"
                "**直接转写**：单进程顺序转写，资源占用低\n\n"
                "**并行转写**：ffmpeg 切块 + 多进程，长音频速度更快"
            ),
        )

        # ── 术语词表输入 ──────────────────────────────────────────────────────
        kept = []  # 默认为空，在 expander 内赋值
        with st.expander("📚 自定义术语词表（可选）", expanded=False):
            st.caption("每行一个术语，注入 ASR 提升专有名词识别率。也可粘贴 CSV（逗号或换行分隔）。")

            if "terms_raw" not in st.session_state:
                st.session_state.terms_raw = ""

            terms_raw = st.text_area(
                "术语列表",
                value=st.session_state.terms_raw,
                height=120,
                placeholder="例：\n量子纠缠\nTransformer\n李明（项目负责人）",
                label_visibility="collapsed",
                key="terms_textarea",
            )
            st.session_state.terms_raw = terms_raw

            # 解析并估算 token
            raw_terms = [
                t.strip()
                for part in terms_raw.replace(",", "\n").replace("，", "\n").splitlines()
                for t in [part.strip()] if t.strip()
            ]
            if raw_terms:
                kept, truncated = truncate_terms(raw_terms)
                total_tok = sum(_estimate_tokens(t) + 1 for t in kept)
                if truncated:
                    st.warning(
                        f"⚠️ 词表超出 200 token 限制，已自动截断至前 {len(kept)} 条"
                        f"（共 ~{total_tok} token）。超出部分不会注入 ASR。"
                    )
                else:
                    st.caption(f"✓ {len(kept)} 条术语，约 {total_tok} token（上限 200）")
            else:
                kept = []

        # ── 测试功能：原始文本 & 错词率对比 ─────────────────────────────────
        with st.expander("🧪 测试功能：转录错词率对比（仅供测试，后续将删除）", expanded=False):
            st.warning(
                "⚠️ **测试专用功能**：填入原始文本后，点击「测试转录」将只运行 ASR 并计算错词率，"
                "**不会**生成会议纪要、不保存数据库。"
            )
            ref_text = st.text_area(
                "原始转录文本（参考文本）",
                height=120,
                placeholder="请粘贴音频对应的准确文本，用于计算字符错误率（CER）……",
                key="ref_text_input",
            )

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

        _ref_text = st.session_state.get("ref_text_input", "").strip()
        disabled = not _has_file or (
            selected_scene == _CUSTOM_SCENE and not st.session_state.custom_headings
        )
        cols = st.columns([2, 2, 1])
        with cols[0]:
            clicked = st.button(
                "🚀 开始生成会议纪要",
                type="primary",
                width='stretch',
                disabled=disabled,
                key="btn_generate",
            )
        with cols[1]:
            clicked_test = st.button(
                "🧪 测试转录",
                type="secondary",
                width='stretch',
                disabled=not _has_file,
                key="btn_test_asr",
                help="仅运行 ASR，与原始文本对比错词率，不生成纪要",
            )
        with cols[2]:
            if _ref_text:
                st.caption("✓ 有参考文本")
            else:
                st.caption("⏱ 预计约 2 分钟")

    if not clicked and not clicked_test:
        return

    # ---------- 公共准备 ----------
    reset_result()
    fs = FileService()
    db = MeetingRepository()
    svc = MeetingService(db)

    # 文件路径从 session_state 读取（已在上传时保存，不依赖 uploaded 对象是否仍有效）
    file_path = st.session_state["_saved_file_path"]
    file_hash = st.session_state["_saved_file_hash"]
    ext = st.session_state["_saved_file_ext"]
    file_path = fs.prepare_audio_path(file_path, ext)
    meeting_dt = datetime.combine(meeting_date, meeting_time)

    # 收集场景参数
    is_custom = selected_scene == "自定义模板"
    scene_to_use = PromptTemplateLoader.DEFAULT_SCENE if is_custom else selected_scene
    custom_headings = st.session_state.get("custom_headings") or None

    # 收集术语词表（已在表单中完成截断，这里直接使用 kept）
    terms_to_use = kept if kept else None

    # ── 测试模式：仅 ASR + CER 对比 ─────────────────────────────────────────
    if clicked_test:
        _run_asr_test(file_path, asr_model, terms_to_use, transcription_mode)
        return

    # 进度 UI 区
    st.divider()
    st.caption(f"🤖 ASR 模型：**{asr_model}**" + (f"  |  📚 术语词表：{len(terms_to_use)} 条" if terms_to_use else ""))
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
            scene=scene_to_use,
            custom_headings=custom_headings,
            asr_model=asr_model,
            terms=terms_to_use,
            chunk_strategy=chunk_strategy_label,
            transcription_mode=transcription_mode,
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


# ── 测试功能：ASR 转录 + CER 对比（后续将删除）────────────────────────────────

def _normalize_for_cer(text: str) -> str:
    """去标点空格，保留汉字+字母数字（小写），用于 CER 计算"""
    return re.sub(r"[^一-鿿a-z0-9]", "", text.lower())


def _calculate_cer(reference: str, hypothesis: str) -> float:
    ref = _normalize_for_cer(reference)
    hyp = _normalize_for_cer(hypothesis)
    if not ref:
        return 0.0
    # Levenshtein 编辑距离（字符级）
    n, m = len(ref), len(hyp)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, m + 1):
            prev, dp[j] = dp[j], min(
                prev + (0 if ref[i - 1] == hyp[j - 1] else 1),
                dp[j] + 1, dp[j - 1] + 1,
            )
    return dp[m] / n


def _build_diff_html(reference: str, hypothesis: str) -> str:
    """对比 hypothesis 与 reference，将 hypothesis 中不匹配的字符标红，返回 HTML"""
    ref_chars = list(reference)
    hyp_chars = list(hypothesis)
    matcher = difflib.SequenceMatcher(None, ref_chars, hyp_chars, autojunk=False)
    parts = []
    for op, _, _, j1, j2 in matcher.get_opcodes():
        chunk = html.escape("".join(hyp_chars[j1:j2]))
        if op == "equal":
            parts.append(chunk)
        else:
            parts.append(f'<span style="color:#EF4444;background:#FEF2F2">{chunk}</span>')
    return "".join(parts)


def _run_asr_test(file_path: str, asr_model: str, terms: list | None,
                  transcription_mode: str):
    """测试专用：仅运行 ASR，展示转录结果并（若有参考文本）计算 CER"""
    ref_text = st.session_state.get("ref_text_input", "").strip()

    st.divider()
    st.markdown(
        "### 🧪 转录测试结果\n"
        '<span style="color:#6B7280;font-size:12px">⚠️ 测试功能，仅供转录评估，不生成会议纪要，不保存数据库</span>',
        unsafe_allow_html=True,
    )

    status = st.empty()
    status.markdown("**⏳ 正在加载模型并转写...**")
    prog = st.progress(0)

    try:
        if asr_model == ASR_MODEL_SENSEVOICE:
            from engines.sense_voice_engine import SenseVoiceEngine
            engine = SenseVoiceEngine()
        else:
            from engines.asr_engine import ASREngine
            engine = ASREngine()

        t0 = _time.time()
        if transcription_mode == "parallel":
            segments = []
            for event in engine.transcribe_parallel_iter(file_path, terms=terms):
                if event["type"] == "chunk_done":
                    prog.progress(min(int(event["completed"] / max(event["total"], 1) * 90), 90))
                elif event["type"] == "complete":
                    segments = event["segments"]
        else:
            segments = []
            for seg, _ in engine.transcribe_iter(file_path, terms=terms):
                segments.append(seg)
                prog.progress(min(len(segments) * 5, 90))

        asr_time = _time.time() - t0
        hyp_text = " ".join(seg.get("text", "") for seg in segments)

    except Exception as e:
        status.error(f"转写失败：{e}")
        prog.empty()
        return

    prog.progress(100)

    # ── 展示 ──────────────────────────────────────────────────────────────────
    if ref_text:
        cer = _calculate_cer(ref_text, hyp_text)
        c1, c2 = st.columns(2)
        with c1:
            st.metric("字符错误率（CER）", f"{cer * 100:.2f}%")
        with c2:
            st.metric("转写耗时", f"{asr_time:.1f}s")

        status.success(f"✅ 转写完成  |  CER {cer*100:.2f}%  |  耗时 {asr_time:.1f}s")

        col_ref, col_hyp = st.columns(2, gap="medium")
        with col_ref:
            st.markdown("**📄 原始文本（参考）**")
            st.markdown(
                f'<div style="background:#F8FAFC;padding:12px;border-radius:6px;'
                f'font-size:14px;line-height:1.8;border:1px solid #E2E8F0;'
                f'max-height:400px;overflow-y:auto">'
                f'{html.escape(ref_text)}</div>',
                unsafe_allow_html=True,
            )
        with col_hyp:
            st.markdown(f"**🎤 转录结果（{asr_model}）**")
            diff_html = _build_diff_html(ref_text, hyp_text)
            st.markdown(
                f'<div style="background:#F8FAFC;padding:12px;border-radius:6px;'
                f'font-size:14px;line-height:1.8;border:1px solid #E2E8F0;'
                f'max-height:400px;overflow-y:auto">'
                f'{diff_html}</div>',
                unsafe_allow_html=True,
            )
        st.caption("🔴 红色文字 = 与参考文本不一致")
    else:
        status.success(f"✅ 转写完成  |  耗时 {asr_time:.1f}s（未提供参考文本，不计算 CER）")
        st.metric("转写耗时", f"{asr_time:.1f}s")
        st.markdown("**🎤 转录结果**")
        st.text_area("转录全文", value=hyp_text, height=200, disabled=True, key="test_hyp_out")
