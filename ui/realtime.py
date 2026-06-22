# -*- coding: utf-8 -*-
"""实时转写页面

状态机：
  idle       → 点击「开始录制」
  recording  → 实时显示转写文本，点击「结束录音」
  stopped    → 显示全部文本，可选「识别说话人」或直接「生成会议纪要」
  diarizing  → 离线说话人识别中（30–90s）
  generating → 同步运行 LLM 流程，完成后跳转 result 页
"""

import hashlib
import queue as _queue
import threading
import time
from datetime import datetime

import streamlit as st

from ui.components import progress_steps
from logger import get_logger

logger = get_logger(__name__)

# 说话人颜色表（最多支持 8 位说话人）
_SPK_COLORS = [
    "#2563EB",  # 说话人1 蓝
    "#059669",  # 说话人2 绿
    "#D97706",  # 说话人3 橙
    "#7C3AED",  # 说话人4 紫
    "#DC2626",  # 说话人5 红
    "#0891B2",  # 说话人6 青
    "#BE185D",  # 说话人7 粉
    "#65A30D",  # 说话人8 草绿
]


def _spk_color(spk: str, spk_index: dict) -> str:
    if spk not in spk_index:
        spk_index[spk] = len(spk_index) % len(_SPK_COLORS)
    return _SPK_COLORS[spk_index[spk]]


def _fmt_ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def _fmt_duration(elapsed: float) -> str:
    h = int(elapsed // 3600)
    m = int((elapsed % 3600) // 60)
    s = int(elapsed % 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _cleanup():
    svc = st.session_state.get("rt_service")
    if svc and svc.is_running():
        try:
            svc.stop()
        except Exception:
            pass


def _reset_rt_state():
    for k in list(st.session_state.keys()):
        if k.startswith("rt_"):
            del st.session_state[k]


# ── 文本渲染 ──────────────────────────────────────────────────────────────────

def _render_text(text: str, streaming: bool = False):
    """渲染纯累积转写文本（无说话人标注）。"""
    if not text:
        return
    cursor = '<span style="color:#94A3B8"> ▌</span>' if streaming else ""
    st.markdown(
        f'<div style="font-size:14px;line-height:1.9;color:#1E293B;'
        f'white-space:pre-wrap;word-break:break-all">{text}{cursor}</div>',
        unsafe_allow_html=True,
    )


def _render_diar_segments(segments: list):
    """渲染带说话人标注的分句列表，不同说话人用不同颜色区分。"""
    if not segments:
        st.warning("未识别到任何发言内容。")
        return

    spk_index: dict = {}
    lines = []
    prev_spk = None
    for seg in segments:
        spk = seg.get("spk", "说话人1")
        text = seg.get("text", "").strip()
        if not text:
            continue
        color = _spk_color(spk, spk_index)
        # 同一说话人连续发言不重复显示标签
        label = (
            f'<span style="font-weight:700;color:{color};margin-right:6px">[{spk}]</span>'
            if spk != prev_spk
            else f'<span style="color:{color};margin-right:6px">　　</span>'
        )
        lines.append(
            f'<div style="margin-bottom:6px;font-size:14px;line-height:1.7;color:#1E293B">'
            f'{label}{text}</div>'
        )
        prev_spk = spk

    # 图例
    legend_items = []
    for spk, idx in sorted(spk_index.items(), key=lambda x: x[1]):
        c = _SPK_COLORS[idx % len(_SPK_COLORS)]
        legend_items.append(
            f'<span style="display:inline-flex;align-items:center;margin-right:14px">'
            f'<span style="width:10px;height:10px;border-radius:50%;background:{c};'
            f'display:inline-block;margin-right:4px"></span>'
            f'<span style="font-size:12px;color:#64748B">{spk}</span></span>'
        )
    legend_html = (
        f'<div style="margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #F1F5F9">'
        f'{"".join(legend_items)}</div>'
        if legend_items
        else ""
    )

    st.markdown(legend_html + "\n".join(lines), unsafe_allow_html=True)


# ── 阶段纪要 ─────────────────────────────────────────────────────────────────

_SUMMARY_INTERVAL = 120   # 每 2 分钟触发一次阶段纪要


def _generate_segment_summary(text: str) -> str:
    """在后台线程中调用 LLM，对 text 生成简洁阶段纪要。失败时抛出异常由调用方捕获。"""
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import PromptTemplate
    from engines.llm import get_llm

    llm = get_llm(temperature=0.1)
    prompt = PromptTemplate.from_template(
        "你是专业会议记录员。以下是最近一段时间的会议转写内容：\n\n{text}\n\n"
        "请用3-5句话生成本阶段的核心纪要，聚焦重要议题与关键决定，语言简洁专业，直接输出纪要内容。"
    )
    chain = prompt | llm | StrOutputParser()
    result = chain.invoke({"text": text[:3000]})
    return (result or "").strip() or "（本阶段无有效摘要）"


def _render_segment_notes(notes: list):
    """将阶段纪要列表以追加方式渲染，不覆盖前一段。"""
    for note in notes:
        idx = note.get("index", "?")
        ts = note.get("time", "")
        text = note.get("text", "")
        st.markdown(
            f'<div style="border-left:3px solid #3B82F6;padding:0.5rem 0.75rem;'
            f'margin-bottom:0.6rem;background:#F8FAFC;border-radius:0 6px 6px 0">'
            f'<div style="font-size:12px;color:#64748B;margin-bottom:3px">'
            f'第 {idx} 段 · {ts}</div>'
            f'<div style="font-size:14px;color:#1E293B;line-height:1.7">{text}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _tick_summary(svc, elapsed: float):
    """每次 rerun 时调用：消费队列、按时触发新摘要。不抛出任何异常。"""
    # 初始化 session state
    if "rt_summary_queue" not in st.session_state:
        st.session_state.rt_summary_queue = _queue.Queue()
    if "rt_segment_notes" not in st.session_state:
        st.session_state.rt_segment_notes = []
    if "rt_last_summary_time" not in st.session_state:
        st.session_state.rt_last_summary_time = time.time()

    # 消费后台已完成的摘要
    q: _queue.Queue = st.session_state.rt_summary_queue
    while not q.empty():
        try:
            note = q.get_nowait()
            st.session_state.rt_segment_notes.append(note)
        except _queue.Empty:
            break

    # 检查是否到达 2 分钟触发点
    time_since = time.time() - st.session_state.rt_last_summary_time
    summary_thread: threading.Thread | None = st.session_state.get("rt_summary_thread")
    thread_alive = summary_thread is not None and summary_thread.is_alive()

    if time_since < _SUMMARY_INTERVAL or thread_alive:
        return

    window_text, new_pos = svc.get_text_window()
    if not window_text.strip():
        # 无新内容，延迟下次触发时间避免空轮询
        st.session_state.rt_last_summary_time = time.time()
        return

    # 先更新时间戳，checkpoint 留到 LLM 成功后再推进，失败可在下轮重试
    st.session_state.rt_last_summary_time = time.time()
    note_ts = _fmt_duration(elapsed)
    note_idx = len(st.session_state.rt_segment_notes) + 1

    def _bg(text, ts, idx, out_q, _svc, pos):
        try:
            summary = _generate_segment_summary(text)
            _svc.advance_checkpoint(pos)   # 仅成功后推进，失败则下轮包含同段重试
            out_q.put({"index": idx, "time": ts, "text": summary})
        except Exception as exc:
            logger.warning("阶段纪要生成失败（第 %s 段），下轮将重试: %s", idx, exc)

    t = threading.Thread(
        target=_bg,
        args=(window_text, note_ts, note_idx, q, svc, new_pos),
        daemon=True,
        name=f"segment-summary-{note_idx}",
    )
    t.start()
    st.session_state.rt_summary_thread = t


# ── 各状态渲染函数 ────────────────────────────────────────────────────────────

def _render_idle():
    st.markdown(
        '<div style="text-align:center;padding:2.5rem 0 1.5rem 0">'
        '<div style="font-size:3rem;margin-bottom:0.75rem">🎙️</div>'
        '<div style="font-size:15px;color:#64748B;line-height:1.6">'
        "点击下方按钮，开始通过麦克风录音并实时转写会议内容<br>"
        "录音结束后可识别说话人，再生成会议纪要"
        "</div></div>",
        unsafe_allow_html=True,
    )
    _, col, _ = st.columns([1, 2, 1])
    with col:
        if st.button("🎙️ 开始录制", key="rt_btn_start", type="primary", use_container_width=True):
            _do_start_recording()


def _do_start_recording():
    from services.realtime_asr_service import get_realtime_service

    svc = get_realtime_service()
    with st.spinner("正在加载 FunASR 语音识别模型（首次约需 30–60s）…"):
        try:
            svc.initialize()
        except Exception as exc:
            st.error(f"模型加载失败：{exc}\n\n请确认已安装 funasr / sounddevice，且网络可访问 ModelScope。")
            return

    try:
        svc.start()
    except Exception as exc:
        st.error(f"麦克风启动失败：{exc}\n\n请检查麦克风权限和 sounddevice 安装。")
        return

    st.session_state.rt_service = svc
    st.session_state.rt_state = "recording"
    st.session_state.rt_start_time = time.time()
    st.rerun()


def _render_recording():
    svc = st.session_state.get("rt_service")
    if svc is None:
        st.session_state.rt_state = "idle"
        st.rerun()
        return

    # 检测后台线程是否异常退出
    err = svc.get_error()
    if err:
        st.error(f"录音线程异常退出：{err}")
        salvaged_text = svc.get_text()
        try:
            audio_path = svc.stop()
        except Exception:
            audio_path = ""
        if salvaged_text:
            st.info(f"已保留 {len(salvaged_text)} 字的识别内容，可继续生成纪要。")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("查看已识别内容", key="rt_crash_view"):
                    st.session_state.rt_text = salvaged_text
                    st.session_state.rt_duration = svc.get_duration()
                    st.session_state.rt_audio_path = audio_path
                    st.session_state.pop("rt_diar_segments", None)
                    st.session_state.rt_state = "stopped"
                    st.rerun()
            with col_b:
                if st.button("重新录制", key="rt_crash_retry"):
                    _reset_rt_state()
                    st.rerun()
        else:
            if st.button("重新录制", key="rt_crash_retry"):
                _reset_rt_state()
                st.rerun()
        return

    current_text = svc.get_text()
    elapsed = time.time() - (st.session_state.rt_start_time or time.time())

    # 每次刷新都检查阶段纪要定时器（消费队列 + 按需触发新任务）
    _tick_summary(svc, elapsed)

    # ── 录音状态栏 ──────────────────────────────────────────────────────────
    next_summary_in = max(0, _SUMMARY_INTERVAL - (time.time() - st.session_state.get("rt_last_summary_time", time.time())))
    thread_alive = (
        st.session_state.get("rt_summary_thread") is not None
        and st.session_state["rt_summary_thread"].is_alive()
    )
    status_right = (
        '<span style="font-size:12px;color:#DC2626">🔄 生成阶段纪要中…</span>'
        if thread_alive
        else f'<span style="font-size:12px;color:#DC2626">下段纪要 {int(next_summary_in)}s 后</span>'
    )

    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'background:#FEF2F2;border:1px solid #FECACA;border-radius:12px;'
        f'padding:0.6rem 1.2rem;margin-bottom:1rem">'
        f'<span style="color:#DC2626;font-weight:700;font-size:15px">● 录音中</span>'
        f'<span style="font-family:monospace;font-size:15px;font-weight:600;color:#DC2626">'
        f'{_fmt_duration(elapsed)}</span>'
        f'{status_right}</div>',
        unsafe_allow_html=True,
    )

    _, col, _ = st.columns([1, 2, 1])
    with col:
        if st.button("⏹ 结束录音", key="rt_btn_stop", type="primary", use_container_width=True):
            _do_stop_recording(svc)
            return

    # ── 阶段纪要列表（追加显示，不覆盖）───────────────────────────────────
    notes = st.session_state.get("rt_segment_notes", [])
    if notes:
        st.markdown("#### 阶段纪要")
        with st.container(border=True):
            _render_segment_notes(notes)

    # ── 实时转写 ────────────────────────────────────────────────────────────
    st.markdown("#### 实时转写")
    with st.container(border=True):
        if current_text:
            _render_text(current_text, streaming=True)
        else:
            st.markdown(
                '<div style="color:#94A3B8;font-size:14px">正在等待语音输入…</div>',
                unsafe_allow_html=True,
            )

    time.sleep(1)
    st.rerun()


def _do_stop_recording(svc):
    with st.spinner("正在处理最后一段语音…"):
        try:
            audio_path = svc.stop()
        except Exception as exc:
            logger.warning("停止录音时出错，尝试保留已识别内容: %s", exc)
            audio_path = ""
        final_text = svc.get_text()
        duration_s = svc.get_duration()

    st.session_state.rt_text = final_text
    st.session_state.rt_duration = duration_s
    st.session_state.rt_audio_path = audio_path
    st.session_state.pop("rt_diar_segments", None)   # 清除上次说话人结果
    st.session_state.rt_state = "stopped"
    st.rerun()


def _render_stopped():
    full_text = st.session_state.get("rt_text", "")
    duration_s = st.session_state.get("rt_duration", 0.0)
    diar_segs: list | None = st.session_state.get("rt_diar_segments")   # None = 未运行过
    has_audio = bool(st.session_state.get("rt_audio_path"))

    char_count = len(full_text)
    st.success(
        f"录音已结束 · 时长约 **{_fmt_duration(duration_s)}** · 识别 **{char_count}** 字"
    )

    # ── 阶段纪要（录音中生成的，追加展示）──────────────────────────────────
    notes = st.session_state.get("rt_segment_notes", [])
    if notes:
        with st.expander(f"📋 阶段纪要（共 {len(notes)} 段）", expanded=True):
            _render_segment_notes(notes)

    # ── 转写结果区 ──────────────────────────────────────────────────────────
    st.markdown("#### 转写结果")
    with st.container(border=True):
        if diar_segs is not None:
            # 已完成说话人识别 → 彩色展示
            _render_diar_segments(diar_segs)
        elif full_text:
            _render_text(full_text)
        else:
            st.warning("未识别到任何有效语音，请确认麦克风输入正常后重试。")

    # ── 说话人识别按钮 ──────────────────────────────────────────────────────
    if has_audio and diar_segs is None:
        st.markdown(
            '<div style="font-size:12px;color:#94A3B8;margin:4px 0 2px 0">'
            "识别不同说话人的发言，适合多人会议（需额外 30–90 秒）</div>",
            unsafe_allow_html=True,
        )
        if st.button(
            "🎙 识别说话人",
            key="rt_btn_diarize",
            type="secondary",
            use_container_width=False,
        ):
            st.session_state.rt_state = "diarizing"
            st.rerun()
    elif diar_segs is not None:
        if st.button("↩ 清除说话人标注", key="rt_btn_clear_diar", type="tertiary"):
            st.session_state.pop("rt_diar_segments", None)
            st.rerun()

    st.divider()

    # ── 生成会议纪要表单 ────────────────────────────────────────────────────
    st.markdown("#### 生成会议纪要")
    with st.container(border=True):
        default_title = f"实时会议_{datetime.now().strftime('%Y%m%d_%H%M')}"
        title = st.text_input("会议标题", value=default_title)
        c1, c2 = st.columns(2)
        with c1:
            meeting_date = st.date_input("日期", value=datetime.now())
        with c2:
            meeting_time = st.time_input("时间", value=datetime.now().time())
        output_format = st.selectbox("导出格式", ["docx", "md", "pdf"], index=0)

    st.markdown('<div style="padding:0.25rem 0"></div>', unsafe_allow_html=True)

    col_gen, col_retry = st.columns([2, 1])
    with col_gen:
        if st.button(
            "🤖 生成会议纪要",
            key="rt_btn_generate",
            type="primary",
            use_container_width=True,
            disabled=not full_text,
        ):
            st.session_state.rt_gen_title = title
            st.session_state.rt_gen_date = meeting_date
            st.session_state.rt_gen_time = meeting_time
            st.session_state.rt_gen_format = output_format
            st.session_state.rt_state = "generating"
            st.rerun()
    with col_retry:
        if st.button("🔄 重新录制", key="rt_btn_retry", type="secondary", use_container_width=True):
            _cleanup()
            _reset_rt_state()
            st.rerun()


def _render_diarizing():
    """离线说话人识别状态：同步运行 run_diarization，完成后回到 stopped。"""
    audio_path = st.session_state.get("rt_audio_path", "")
    svc = st.session_state.get("rt_service")

    if not svc or not audio_path:
        st.session_state.rt_state = "stopped"
        st.rerun()
        return

    st.info("🎙 正在识别说话人，请稍候（约 30–90 秒）…")
    progress = st.progress(0, text="加载离线说话人识别模型…")

    try:
        # 加载模型阶段
        svc._init_spk_model()
        progress.progress(30, text="模型就绪，正在分析音频…")

        diar_segs = svc.run_diarization(audio_path)
        progress.progress(100, text="识别完成")

    except Exception as exc:
        progress.empty()
        st.error(f"说话人识别失败：{exc}")
        if st.button("← 返回", key="rt_diar_back"):
            st.session_state.rt_state = "stopped"
            st.rerun()
        return

    if diar_segs:
        spk_set = {s["spk"] for s in diar_segs}
        st.success(f"识别完成，共发现 **{len(spk_set)}** 位说话人，**{len(diar_segs)}** 段发言")
    else:
        st.warning("未能识别出说话人信息，可能是音频质量较低或说话人发言过短。")

    st.session_state.rt_diar_segments = diar_segs
    st.session_state.rt_state = "stopped"
    time.sleep(1)
    st.rerun()


def _render_generating():
    """同步运行 LLM 流程，完成后跳转 result 页。"""
    from datetime import datetime as dt

    from db.repository import MeetingRepository
    from services.meeting_service import MeetingService

    full_text = st.session_state.get("rt_text", "")
    duration_s = st.session_state.get("rt_duration", 0.0)
    diar_segs: list | None = st.session_state.get("rt_diar_segments")
    audio_path = st.session_state.get("rt_audio_path", "")
    title = st.session_state.get("rt_gen_title", "实时会议")
    meeting_date = st.session_state.get("rt_gen_date", datetime.now().date())
    meeting_time = st.session_state.get("rt_gen_time", datetime.now().time())
    output_format = st.session_state.get("rt_gen_format", "docx")
    meeting_dt = dt.combine(meeting_date, meeting_time)

    # 有说话人分段时，用格式化的带标注文本作为 transcript
    if diar_segs:
        transcript_text = "\n".join(
            f"[{s['spk']}] {s['text']}" for s in diar_segs if s.get("text")
        )
        segments = [
            {"text": f"[{s['spk']}] {s['text']}", "start": s.get("start", 0.0), "end": s.get("end", 0.0)}
            for s in diar_segs if s.get("text")
        ]
    else:
        transcript_text = full_text
        segments = [{"text": full_text, "start": 0.0, "end": round(duration_s, 1)}] if full_text else []

    audio_hash = hashlib.sha256((transcript_text + str(time.time())).encode()).hexdigest()

    st.markdown("#### 正在生成会议纪要…")
    status_text = st.empty()
    progress_bar = st.progress(0)
    steps_ph = st.empty()
    with steps_ph.container():
        progress_steps(2)

    def on_progress(pct: int, msg: str):
        progress_bar.progress(min(pct, 100))
        status_text.markdown(f"**{msg}**")
        step = 0 if pct < 55 else (1 if pct < 70 else (2 if pct < 88 else 3))
        with steps_ph.container():
            progress_steps(step)

    try:
        db = MeetingRepository()
        svc = MeetingService(db)
        result = svc.process_from_realtime(
            segments=segments,
            audio_path=audio_path,
            file_hash=audio_hash,
            title=title,
            meeting_dt=meeting_dt,
            output_format=output_format,
            progress_callback=on_progress,
        )
    except Exception as exc:
        progress_bar.empty()
        steps_ph.empty()
        status_text.empty()
        st.error(f"生成失败：{str(exc)[:300]}\n\n请确认 Ollama 服务已启动。")
        if st.button("← 返回修改", key="rt_gen_back"):
            st.session_state.rt_state = "stopped"
            st.rerun()
        return

    progress_bar.progress(100)
    with steps_ph.container():
        progress_steps(4)
    status_text.success("✅ 会议纪要生成完成")

    st.session_state.data = result
    st.session_state.segments = result.get("segments", [])
    st.session_state.output_path = result.get("output_path")
    _reset_rt_state()
    st.session_state.page = "result"
    st.rerun()


# ── 主入口 ────────────────────────────────────────────────────────────────────

def page_realtime():
    if "rt_state" not in st.session_state:
        st.session_state.rt_state = "idle"

    st.markdown(
        '<div style="padding:1rem 0 0.5rem">'
        '<div style="font-size:26px;font-weight:800;letter-spacing:-0.02em;color:#0F172A">'
        "实时转写</div>"
        '<div style="font-size:14px;color:#64748B;margin-top:4px">'
        "开始录音并生成会议纪要"
        "</div></div>",
        unsafe_allow_html=True,
    )

    if st.session_state.rt_state not in ("generating", "diarizing"):
        if st.button("← 返回首页", key="rt_back", type="tertiary"):
            _cleanup()
            _reset_rt_state()
            st.session_state.page = "home"
            st.rerun()

    st.markdown('<div style="padding:0.25rem 0"></div>', unsafe_allow_html=True)

    state = st.session_state.rt_state
    if state == "idle":
        _render_idle()
    elif state == "recording":
        _render_recording()
    elif state == "stopped":
        _render_stopped()
    elif state == "diarizing":
        _render_diarizing()
    elif state == "generating":
        _render_generating()
    else:
        st.session_state.rt_state = "idle"
        st.rerun()
