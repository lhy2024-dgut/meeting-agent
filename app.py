# -*- coding: utf-8 -*-
"""智能会议纪要 Agent — Streamlit 前端入口"""

import streamlit as st

# ---- 页面配置 ----
st.set_page_config(
    page_title="Meeting Agent · 智能会议纪要",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---- 全局 CSS ----
from ui.global_css import inject

inject()

# ---- 全局 Header ----
from ui.components import render_header

render_header()

# ---- 路由初始化 ----
if "page" not in st.session_state:
    st.session_state.page = "home"

# ---- 页面路由 ----
PAGE_MAP = {
    "home": "ui.home",
    "upload": "ui.upload",
    "realtime": "ui.realtime",
    "result": "ui.result",
    "chat": "ui.chat",
    "history": "ui.history",
    "stats": "ui.stats",
    "contacts": "ui.contacts",
}

module_name = PAGE_MAP.get(st.session_state.page, "ui.home")
import importlib
import sys

# 仅在 DEBUG 模式下热重载项目模块，避免生产环境每次路由切换都销毁单例（Whisper/Embeddings/LLM）
import os as _os
if _os.getenv("DEBUG", "").lower() in ("1", "true", "yes"):
    _RELOAD_PREFIXES = ("ui.", "chains.", "services.", "prompts.", "engines.", "agents.", "rag.")
    _mods_to_reload = [k for k in list(sys.modules.keys()) if any(k.startswith(p) for p in _RELOAD_PREFIXES)]
    for _mod in _mods_to_reload:
        sys.modules.pop(_mod, None)

module = importlib.import_module(module_name)

# 将 page_* 函数映射到对应的渲染函数
FUNC_MAP = {
    "home": "page_home",
    "upload": "page_upload",
    "realtime": "page_realtime",
    "result": "page_result",
    "chat": "page_chat",
    "history": "page_history",
    "stats": "page_stats",
    "contacts": "page_contacts",
}

func_name = FUNC_MAP.get(st.session_state.page)
if func_name and hasattr(module, func_name):
    getattr(module, func_name)()
else:
    st.error(f"页面未找到: {st.session_state.page}")
    if st.button("← 返回首页"):
        st.session_state.page = "home"
        st.rerun()
