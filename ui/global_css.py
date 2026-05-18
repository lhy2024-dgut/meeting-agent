# -*- coding: utf-8 -*-
"""全局 CSS 注入 + 主题配置"""

import streamlit as st

PRIMARY = "#5B5EA6"
PRIMARY_HOVER = "#4A4D8C"
ACCENT = "#F29E4C"
ACCENT_HOVER = "#E07B20"
SUCCESS = "#2D9CDB"
DARK = "#1A1A2E"
SURFACE = "#FAFBFC"
CARD_BG = "#FFFFFF"
BORDER = "#E8ECF0"
TEXT = "#1E293B"
MUTED = "#64748B"
LIGHT_FILL = "#F5F6F8"


def inject():
    st.markdown(
        f"""
    <style>
    /* === 全局背景 === */
    .stApp {{
        background-color: {SURFACE};
    }}

    /* === 主内容区居中 === */
    .block-container {{
        max-width: 1024px;
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }}

    /* === 按钮 === */
    .stButton > button {{
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.2s ease;
        border: none;
        padding: 0.5rem 1.25rem;
    }}
    .stButton > button[kind="primary"] {{
        background-color: {PRIMARY};
        color: #FFFFFF;
    }}
    .stButton > button[kind="primary"]:hover {{
        background-color: {PRIMARY_HOVER};
        box-shadow: 0 4px 12px rgba(91, 94, 166, 0.3);
    }}
    .stButton > button[kind="secondary"] {{
        background-color: #FFFFFF;
        color: {PRIMARY};
        border: 1.5px solid {PRIMARY};
    }}
    .stButton > button[kind="secondary"]:hover {{
        background-color: #F5F3FF;
        border-color: {PRIMARY_HOVER};
    }}

    /* === 下载按钮 === */
    .stDownloadButton > button {{
        border-radius: 10px;
        font-weight: 700;
        background-color: {SUCCESS};
        color: #FFFFFF;
        border: none;
        transition: all 0.2s ease;
    }}
    .stDownloadButton > button:hover {{
        background-color: #2389C0;
        box-shadow: 0 4px 12px rgba(45, 156, 219, 0.3);
    }}

    /* === 输入框 === */
    input[data-baseweb="input"] {{
        border-radius: 10px !important;
        border: 1.5px solid {BORDER} !important;
        padding: 0.6rem 1rem !important;
        transition: all 0.2s ease;
    }}
    input[data-baseweb="input"]:focus {{
        border-color: {PRIMARY} !important;
        box-shadow: 0 0 0 3px rgba(91, 94, 166, 0.12) !important;
    }}

    /* === 文本域 === */
    textarea[data-baseweb="textarea"] {{
        border-radius: 10px !important;
        border: 1.5px solid {BORDER} !important;
    }}

    /* === Selectbox === */
    [data-baseweb="select"] {{
        border-radius: 10px;
    }}

    /* === Tab 导航 === */
    button[data-baseweb="tab"] {{
        font-weight: 600 !important;
        font-size: 15px !important;
        padding: 0.6rem 1.2rem !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {PRIMARY} !important;
    }}

    /* === 文件上传区 === */
    [data-testid="stFileUploader"] {{
        border: 2px dashed {BORDER};
        border-radius: 20px;
        padding: 2.5rem 2rem;
        background: {SURFACE};
        transition: all 0.3s ease;
    }}
    [data-testid="stFileUploader"]:hover {{
        border-color: {PRIMARY};
        background: #F8F7FF;
    }}
    [data-testid="stFileUploader"] section {{
        border: none !important;
    }}

    /* === 文件上传区拖拽激活态 === */
    [data-testid="stFileUploader"][data-testid="stFileUploader"]:active {{
        border-color: {ACCENT};
        background: #FFFBF0;
    }}

    /* === 卡片容器 (st.container border=True) === */
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background: {CARD_BG};
        border: 1px solid {BORDER} !important;
        border-radius: 16px !important;
        transition: box-shadow 0.25s ease;
    }}
    [data-testid="stVerticalBlockBorderWrapper"]:hover {{
        box-shadow: 0 8px 28px rgba(0, 0, 0, 0.06);
    }}

    /* === 滚动条 === */
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: {SURFACE}; }}
    ::-webkit-scrollbar-thumb {{ background: #CBD5E1; border-radius: 3px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: #94A3B8; }}

    /* === Header 占位符隐藏（用自定义 header 替代） === */
    header[data-testid="stHeader"] {{
        background: transparent;
    }}

    /* === Sidebar 美化 === */
    [data-testid="stSidebar"] {{
        background-color: {DARK};
    }}
    [data-testid="stSidebar"] * {{
        color: #E2E8F0;
    }}
    [data-testid="stSidebar"] button {{
        background-color: transparent;
        color: #E2E8F0 !important;
    }}

    /* === 自定义 Header === */
    .app-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.75rem 0;
        margin-bottom: 1.5rem;
        border-bottom: 1px solid {BORDER};
    }}
    .app-logo {{
        font-size: 20px;
        font-weight: 800;
        color: {DARK};
        letter-spacing: -0.02em;
    }}
    .app-nav {{
        display: flex;
        gap: 0.5rem;
    }}

    /* === Hero 区域 === */
    .hero-title {{
        font-size: 32px;
        font-weight: 800;
        color: {DARK};
        letter-spacing: -0.03em;
        line-height: 1.2;
        margin-bottom: 0.5rem;
        text-align: center;
    }}
    .hero-subtitle {{
        font-size: 16px;
        color: {MUTED};
        line-height: 1.6;
        text-align: center;
        margin-bottom: 2rem;
    }}

    /* === 步骤进度 === */
    .step-circle {{
        width: 48px;
        height: 48px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        transition: all 0.3s ease;
    }}
    .step-label {{
        margin-top: 8px;
        font-size: 13px;
        font-weight: 600;
    }}

    /* === 统计卡片 === */
    .metric-card {{
        background: {CARD_BG};
        border: 1px solid {BORDER};
        border-radius: 14px;
        padding: 1rem 1.2rem;
        text-align: center;
    }}
    .metric-value {{
        font-size: 28px;
        font-weight: 700;
        color: {DARK};
        line-height: 1.2;
    }}
    .metric-label {{
        font-size: 12px;
        color: {MUTED};
        margin-top: 4px;
    }}

    /* === 待办卡片 === */
    .todo-item {{
        display: flex;
        align-items: flex-start;
        gap: 0.75rem;
        padding: 0.6rem 0;
    }}
    .todo-dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: {ACCENT};
        margin-top: 6px;
        flex-shrink: 0;
    }}
    .todo-content {{
        flex: 1;
    }}
    .todo-text {{
        font-size: 15px;
        color: {TEXT};
        line-height: 1.5;
    }}
    .todo-meta {{
        font-size: 12px;
        color: {MUTED};
        margin-top: 2px;
    }}

    /* === 决议条目 === */
    .decision-item {{
        border-left: 4px solid {PRIMARY};
        padding: 0.5rem 0 0.5rem 1rem;
        margin-bottom: 0.75rem;
        background: {LIGHT_FILL};
        border-radius: 0 8px 8px 0;
    }}
    .decision-number {{
        font-weight: 700;
        color: {PRIMARY};
        font-size: 13px;
        margin-bottom: 2px;
    }}
    .decision-text {{
        font-size: 15px;
        color: {TEXT};
        line-height: 1.6;
    }}

    /* === 纪要纸感容器 === */
    .minutes-paper {{
        max-width: 740px;
        margin: 0 auto;
        background: #FFFFFF;
        padding: 2rem 2.5rem;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        line-height: 1.8;
        font-size: 15px;
        color: {TEXT};
    }}

    /* === 转录文本 === */
    .transcript-line {{
        padding: 0.35rem 0;
        font-size: 14px;
        line-height: 1.7;
        color: {TEXT};
    }}
    .transcript-ts {{
        display: inline-block;
        font-size: 12px;
        color: {MUTED};
        background: {LIGHT_FILL};
        padding: 1px 8px;
        border-radius: 4px;
        margin-right: 8px;
        font-family: "SF Mono", "Consolas", "Menlo", monospace;
    }}

    /* === 状态 Pill === */
    .pill {{
        display: inline-block;
        padding: 2px 12px;
        border-radius: 99px;
        font-size: 12px;
        font-weight: 600;
    }}

    /* === 空态 === */
    .empty-state {{
        text-align: center;
        padding: 3rem 1.5rem;
    }}
    .empty-icon {{
        font-size: 3rem;
        margin-bottom: 1rem;
    }}
    .empty-title {{
        font-size: 18px;
        font-weight: 600;
        color: {TEXT};
        margin-bottom: 0.5rem;
    }}
    .empty-desc {{
        font-size: 14px;
        color: {MUTED};
    }}

    /* === 对话气泡 === */
    .chat-bubble-assistant {{
        background: #F5F3FF;
        border-left: 3px solid {PRIMARY};
        padding: 0.75rem 1rem;
        border-radius: 8px;
        margin-bottom: 0.75rem;
        line-height: 1.6;
        color: #1E293B;
    }}
    .chat-bubble-user {{
        background: {CARD_BG};
        border: 1px solid {BORDER};
        padding: 0.75rem 1rem;
        border-radius: 8px;
        margin-bottom: 0.75rem;
        line-height: 1.6;
        color: #1E293B;
    }}

    /* === CTA 卡片 === */
    .cta-card {{
        background: {CARD_BG};
        border: 1.5px solid {BORDER};
        border-radius: 16px;
        padding: 1.5rem 1rem;
        text-align: center;
        cursor: pointer;
        transition: all 0.25s ease;
    }}
    .cta-card:hover {{
        border-color: {PRIMARY};
        box-shadow: 0 8px 28px rgba(91, 94, 166, 0.08);
    }}
    .cta-icon {{
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }}
    .cta-title {{
        font-size: 16px;
        font-weight: 700;
        color: {DARK};
        margin-bottom: 0.25rem;
    }}
    .cta-desc {{
        font-size: 13px;
        color: {MUTED};
    }}

    /* === 建议问题 === */
    .suggestion-pill {{
        display: inline-block;
        padding: 4px 14px;
        border-radius: 99px;
        background: {LIGHT_FILL};
        color: {PRIMARY};
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        border: 1px solid transparent;
    }}
    .suggestion-pill:hover {{
        border-color: {PRIMARY};
        background: #F5F3FF;
    }}

    /* === 错误状态 === */
    .error-card {{
        background: #FEF2F2;
        border: 1px solid #FECACA;
        border-radius: 14px;
        padding: 2rem 1.5rem;
        text-align: center;
    }}

    /* === 高亮 CTA 按钮 === */
    .btn-accent {{
        background: {ACCENT} !important;
        color: #FFFFFF !important;
        border: none !important;
    }}
    .btn-accent:hover {{
        background: {ACCENT_HOVER} !important;
        box-shadow: 0 4px 14px rgba(242, 158, 76, 0.35) !important;
    }}

    /* === Chat input 美化 === */
    [data-testid="stChatInput"] {{
        border-top: 1px solid {BORDER};
        padding-top: 0.75rem;
    }}

    /* === Dataframe 美化 === */
    .stDataFrame td {{
        padding: 8px 12px !important;
    }}

    /* === Metric === */
    [data-testid="stMetricValue"] {{
        color: {DARK};
        font-weight: 700;
    }}

    /* === Success / Info / Warning / Error 横幅美化 === */
    [data-testid="stSuccess"] div, [data-testid="stInfo"] div {{
        border-radius: 10px;
    }}

    /* === 响应式：窄屏 columns 堆叠 === */
    @media (max-width: 768px) {{
        .block-container {{
            padding: 0.75rem;
        }}
        .hero-title {{
            font-size: 24px;
        }}
        .minutes-paper {{
            padding: 1rem 1.25rem;
        }}
    }}
    </style>
    """,
        unsafe_allow_html=True,
    )
