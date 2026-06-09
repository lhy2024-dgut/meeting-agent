# -*- coding: utf-8 -*-
"""全局 CSS 注入 — 现代精致风格"""

import streamlit as st

PRIMARY = "#6366F1"
PRIMARY_HOVER = "#4F46E5"
PRIMARY_LIGHT = "#EEF2FF"
ACCENT = "#F97316"
ACCENT_HOVER = "#EA580C"
ACCENT_LIGHT = "#FFF7ED"
SUCCESS = "#10B981"
DARK = "#0F172A"
SURFACE = "#F1F5F9"
CARD_BG = "#FFFFFF"
BORDER = "#E2E8F0"
TEXT = "#1E293B"
TEXT_SECONDARY = "#475569"
MUTED = "#94A3B8"
LIGHT_FILL = "#F8FAFC"
GLASS_BG = "rgba(255, 255, 255, 0.72)"


def inject():
    st.markdown(
        f"""
    <style>
    /* ==================================================================
       GLOBAL
       ================================================================== */
    .stApp {{
        background: linear-gradient(180deg, {SURFACE} 0%, #EFF3F8 100%);
        color: {TEXT};
    }}

    .stApp p, .stApp div, .stApp span, .stApp label,
    .stApp h1, .stApp h2, .stApp h3, .stApp h4,
    .stApp li, .stApp td, .stApp th,
    .stApp [data-testid="stMarkdownContainer"] {{
        color: {TEXT};
    }}
    .stApp [data-testid="stCaption"] {{
        color: {MUTED};
    }}
    .stApp h1, .stApp h2, .stApp h3, .stApp h4 {{
        color: {DARK};
        letter-spacing: -0.02em;
    }}

    .block-container {{
        max-width: 1024px;
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }}

    /* ==================================================================
       SCROLLBAR
       ================================================================== */
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: #CBD5E1; border-radius: 3px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: #94A3B8; }}

    /* ==================================================================
       BUTTONS
       ================================================================== */
    .stButton > button {{
        border-radius: 12px;
        font-weight: 600;
        font-size: 14px;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        border: none;
        padding: 0.55rem 1.35rem;
        letter-spacing: -0.01em;
    }}
    .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_HOVER} 100%);
        color: #FFFFFF;
        box-shadow: 0 2px 8px rgba(99, 102, 241, 0.25);
    }}
    .stButton > button[kind="primary"]:hover {{
        box-shadow: 0 6px 20px rgba(99, 102, 241, 0.35);
        transform: translateY(-1px);
    }}
    .stButton > button[kind="primary"]:active {{
        transform: translateY(0);
        box-shadow: 0 1px 4px rgba(99, 102, 241, 0.2);
    }}
    .stButton > button[kind="secondary"] {{
        background: {CARD_BG};
        color: {PRIMARY};
        border: 1.5px solid {BORDER};
    }}
    .stButton > button[kind="secondary"]:hover {{
        background: {PRIMARY_LIGHT};
        border-color: {PRIMARY};
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
    }}
    .stButton > button[kind="tertiary"] {{
        background: transparent;
        color: {TEXT_SECONDARY};
    }}
    .stButton > button[kind="tertiary"]:hover {{
        background: {LIGHT_FILL};
        color: {TEXT};
    }}

    /* ==================================================================
       DOWNLOAD BUTTON
       ================================================================== */
    .stDownloadButton > button {{
        border-radius: 12px;
        font-weight: 600;
        font-size: 14px;
        background: linear-gradient(135deg, {SUCCESS} 0%, #059669 100%);
        color: #FFFFFF;
        border: none;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 2px 8px rgba(16, 185, 129, 0.25);
    }}
    .stDownloadButton > button:hover {{
        box-shadow: 0 6px 20px rgba(16, 185, 129, 0.35);
        transform: translateY(-1px);
    }}

    /* ==================================================================
       INPUTS
       ================================================================== */
    input[data-baseweb="input"] {{
        border-radius: 12px !important;
        border: 1.5px solid {BORDER} !important;
        padding: 0.65rem 1rem !important;
        transition: all 0.2s ease !important;
        font-size: 14px !important;
    }}
    input[data-baseweb="input"]:focus {{
        border-color: {PRIMARY} !important;
        box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.10) !important;
    }}

    textarea[data-baseweb="textarea"] {{
        border-radius: 12px !important;
        border: 1.5px solid {BORDER} !important;
    }}
    textarea[data-baseweb="textarea"]:focus {{
        border-color: {PRIMARY} !important;
        box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.10) !important;
    }}

    [data-baseweb="select"] {{
        border-radius: 12px;
    }}

    /* ==================================================================
       TABS
       ================================================================== */
    button[data-baseweb="tab"] {{
        font-weight: 600 !important;
        font-size: 14px !important;
        padding: 0.6rem 1.2rem !important;
        transition: color 0.2s ease !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {PRIMARY} !important;
    }}

    /* ==================================================================
       FILE UPLOAD ZONE
       ================================================================== */
    [data-testid="stFileUploader"] {{
        border: 2px dashed {BORDER};
        border-radius: 20px;
        padding: 3rem 2rem;
        background: {GLASS_BG};
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }}
    [data-testid="stFileUploader"]:hover {{
        border-color: {PRIMARY};
        background: rgba(238, 242, 255, 0.6);
        box-shadow: 0 0 0 8px rgba(99, 102, 241, 0.04);
    }}
    [data-testid="stFileUploader"] section {{
        border: none !important;
    }}

    /* ==================================================================
       CARDS  (st.container border=True)
       ================================================================== */
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background: {CARD_BG};
        border: 1px solid {BORDER} !important;
        border-radius: 18px !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.03);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }}
    [data-testid="stVerticalBlockBorderWrapper"]:hover {{
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06), 0 2px 4px rgba(0, 0, 0, 0.04);
        border-color: #CBD5E1 !important;
        transform: translateY(-1px);
    }}

    /* ==================================================================
       HEADER
       ================================================================== */
    header[data-testid="stHeader"] {{
        background: transparent;
    }}

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

    /* ==================================================================
       SIDEBAR
       ================================================================== */
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {DARK} 0%, #1E293B 100%);
    }}
    [data-testid="stSidebar"] * {{
        color: #E2E8F0;
    }}
    [data-testid="stSidebar"] button {{
        background: transparent;
        color: #E2E8F0 !important;
    }}

    /* ==================================================================
       HERO
       ================================================================== */
    .hero-title {{
        font-size: 34px;
        font-weight: 800;
        color: {DARK};
        letter-spacing: -0.03em;
        line-height: 1.15;
        margin-bottom: 0.5rem;
        text-align: center;
    }}
    .hero-title span {{
        background: linear-gradient(135deg, {PRIMARY} 0%, {ACCENT} 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }}
    .hero-subtitle {{
        font-size: 16px;
        color: {TEXT_SECONDARY};
        line-height: 1.7;
        text-align: center;
        margin-bottom: 2rem;
    }}

    /* ==================================================================
       CTA CARDS
       ================================================================== */
    .cta-card {{
        background: {CARD_BG};
        border: 1px solid {BORDER};
        border-radius: 18px;
        padding: 1.75rem 1.25rem;
        text-align: center;
        cursor: pointer;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
    }}
    .cta-card:hover {{
        border-color: {PRIMARY};
        box-shadow: 0 12px 32px rgba(99, 102, 241, 0.10);
        transform: translateY(-2px);
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

    /* ==================================================================
       STEP PROGRESS
       ================================================================== */
    .step-circle {{
        width: 48px;
        height: 48px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
    }}
    .step-label {{
        margin-top: 8px;
        font-size: 13px;
        font-weight: 600;
    }}

    /* ==================================================================
       METRIC CARDS
       ================================================================== */
    .metric-card {{
        background: {CARD_BG};
        border: 1px solid {BORDER};
        border-radius: 16px;
        padding: 1.25rem 1.5rem;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
    }}
    .metric-value {{
        font-size: 32px;
        font-weight: 800;
        color: {DARK};
        line-height: 1.1;
        letter-spacing: -0.02em;
    }}
    .metric-label {{
        font-size: 12px;
        font-weight: 500;
        color: {MUTED};
        margin-top: 4px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}

    /* ==================================================================
       TODO ITEMS
       ================================================================== */
    .todo-item {{
        display: flex;
        align-items: flex-start;
        gap: 0.75rem;
        padding: 0.7rem 0.75rem;
        border-radius: 10px;
        transition: background 0.2s ease;
    }}
    .todo-item:hover {{
        background: {LIGHT_FILL};
    }}
    .todo-dot {{
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: linear-gradient(135deg, {ACCENT} 0%, {ACCENT_HOVER} 100%);
        margin-top: 5px;
        flex-shrink: 0;
        box-shadow: 0 0 0 4px rgba(249, 115, 22, 0.12);
    }}
    .todo-content {{
        flex: 1;
    }}
    .todo-text {{
        font-size: 15px;
        color: {TEXT};
        line-height: 1.55;
    }}
    .todo-meta {{
        font-size: 12px;
        color: {MUTED};
        margin-top: 2px;
    }}

    /* ==================================================================
       DECISION ITEMS
       ================================================================== */
    .decision-item {{
        border-left: 3px solid {PRIMARY};
        padding: 0.65rem 0 0.65rem 1.25rem;
        margin-bottom: 0.75rem;
        background: {PRIMARY_LIGHT};
        border-radius: 0 10px 10px 0;
        transition: all 0.2s ease;
    }}
    .decision-item:hover {{
        border-left-color: {PRIMARY_HOVER};
        background: #E0E5FF;
    }}
    .decision-number {{
        font-weight: 700;
        color: {PRIMARY};
        font-size: 12px;
        margin-bottom: 2px;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }}
    .decision-text {{
        font-size: 15px;
        color: {TEXT};
        line-height: 1.6;
    }}

    /* ==================================================================
       MINUTES PAPER
       ================================================================== */
    .minutes-paper {{
        max-width: 740px;
        margin: 0 auto;
        background: {CARD_BG};
        padding: 2.25rem 2.75rem;
        border-radius: 12px;
        border: 1px solid {BORDER};
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04), 0 4px 16px rgba(0, 0, 0, 0.03);
        line-height: 1.85;
        font-size: 15px;
        color: {TEXT};
    }}

    /* ==================================================================
       TRANSCRIPT
       ================================================================== */
    .transcript-line {{
        padding: 0.4rem 0.5rem;
        font-size: 14px;
        line-height: 1.7;
        color: {TEXT};
        border-radius: 6px;
        transition: background 0.15s ease;
    }}
    .transcript-line:hover {{
        background: {LIGHT_FILL};
    }}
    .transcript-ts {{
        display: inline-block;
        font-size: 11px;
        color: {MUTED};
        background: {LIGHT_FILL};
        padding: 2px 10px;
        border-radius: 6px;
        margin-right: 10px;
        font-family: "SF Mono", "Consolas", "Menlo", monospace;
        font-weight: 500;
    }}

    /* ==================================================================
       PILLS
       ================================================================== */
    .pill {{
        display: inline-block;
        padding: 3px 14px;
        border-radius: 99px;
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.01em;
    }}

    /* ==================================================================
       EMPTY STATE
       ================================================================== */
    .empty-state {{
        text-align: center;
        padding: 4rem 1.5rem;
    }}
    .empty-icon {{
        font-size: 3.5rem;
        margin-bottom: 1rem;
    }}
    .empty-title {{
        font-size: 20px;
        font-weight: 700;
        color: {DARK};
        margin-bottom: 0.5rem;
    }}
    .empty-desc {{
        font-size: 15px;
        color: {MUTED};
    }}

    /* ==================================================================
       CHAT BUBBLES
       ================================================================== */
    .chat-bubble-assistant {{
        background: {PRIMARY_LIGHT};
        border-left: 3px solid {PRIMARY};
        padding: 0.85rem 1.15rem;
        border-radius: 0 12px 12px 12px;
        margin-bottom: 0.75rem;
        line-height: 1.65;
        color: {TEXT};
        box-shadow: 0 1px 3px rgba(99, 102, 241, 0.06);
    }}
    .chat-bubble-user {{
        background: {CARD_BG};
        border: 1px solid {BORDER};
        padding: 0.85rem 1.15rem;
        border-radius: 12px 0 12px 12px;
        margin-bottom: 0.75rem;
        margin-left: 32px;
        line-height: 1.65;
        color: {TEXT};
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
    }}

    /* ==================================================================
       SUGGESTION PILLS
       ================================================================== */
    .suggestion-pill {{
        display: inline-block;
        padding: 6px 16px;
        border-radius: 99px;
        background: {LIGHT_FILL};
        color: {PRIMARY};
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        border: 1px solid transparent;
    }}
    .suggestion-pill:hover {{
        border-color: {PRIMARY};
        background: {PRIMARY_LIGHT};
        box-shadow: 0 2px 8px rgba(99, 102, 241, 0.10);
    }}

    /* ==================================================================
       ERROR STATE
       ================================================================== */
    .error-card {{
        background: #FEF2F2;
        border: 1px solid #FECACA;
        border-radius: 16px;
        padding: 2rem 1.5rem;
        text-align: center;
        box-shadow: 0 1px 3px rgba(239, 68, 68, 0.06);
    }}

    /* ==================================================================
       METRIC (Streamlit native)
       ================================================================== */
    [data-testid="stMetricValue"] {{
        color: {DARK};
        font-weight: 700;
    }}

    /* ==================================================================
       ALERT BANNERS
       ================================================================== */
    [data-testid="stSuccess"] div,
    [data-testid="stInfo"] div,
    [data-testid="stWarning"] div,
    [data-testid="stError"] div {{
        border-radius: 12px;
    }}

    /* ==================================================================
       CHAT INPUT
       ================================================================== */
    [data-testid="stChatInput"] {{
        border-top: 1px solid {BORDER};
        padding-top: 0.75rem;
    }}

    /* ==================================================================
       DATAFRAME
       ================================================================== */
    .stDataFrame td {{
        padding: 8px 12px !important;
    }}

    /* ==================================================================
       DIVIDER
       ================================================================== */
    hr {{
        border-color: {BORDER};
        margin: 1.5rem 0;
    }}

    /* ==================================================================
       EXPANDER
       ================================================================== */
    [data-testid="stExpander"] summary {{
        font-weight: 600;
        color: {TEXT_SECONDARY};
    }}

    /* ==================================================================
       RESPONSIVE
       ================================================================== */
    @media (max-width: 768px) {{
        .block-container {{
            padding: 0.75rem;
        }}
        .hero-title {{
            font-size: 26px;
        }}
        .minutes-paper {{
            padding: 1.25rem 1.5rem;
        }}
        .chat-bubble-user {{
            margin-left: 16px;
        }}
    }}

    @media (prefers-reduced-motion: reduce) {{
        *, *::before, *::after {{
            animation-duration: 0.01ms !important;
            transition-duration: 0.01ms !important;
        }}
    }}

    /* ==================================================================
       DARK MODE
       ================================================================== */
    @media (prefers-color-scheme: dark) {{
        .stApp {{
            background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%);
        }}
        .stApp p, .stApp div, .stApp span, .stApp label,
        .stApp h1, .stApp h2, .stApp h3, .stApp h4,
        .stApp li, .stApp td, .stApp th,
        .stApp [data-testid="stMarkdownContainer"] {{
            color: #E2E8F0;
        }}
        .stApp h1, .stApp h2, .stApp h3, .stApp h4 {{
            color: #F1F5F9;
        }}
        [data-testid="stVerticalBlockBorderWrapper"] {{
            background: #1E293B !important;
            border-color: #334155 !important;
        }}
        [data-testid="stVerticalBlockBorderWrapper"]:hover {{
            border-color: #475569 !important;
        }}
        .cta-card, .metric-card, .minutes-paper {{
            background: #1E293B;
            border-color: #334155;
        }}
        .minutes-paper {{
            color: #E2E8F0;
        }}
        .chat-bubble-user {{
            background: #1E293B;
            border-color: #334155;
        }}
        .chat-bubble-assistant {{
            background: rgba(99, 102, 241, 0.15);
        }}
        input[data-baseweb="input"],
        textarea[data-baseweb="textarea"] {{
            background: #1E293B !important;
            color: #E2E8F0 !important;
            border-color: #475569 !important;
        }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%);
        }}
        .stButton > button[kind="secondary"] {{
            background: #1E293B;
            color: #818CF8;
            border-color: #475569;
        }}
        .stButton > button[kind="secondary"]:hover {{
            background: rgba(99, 102, 241, 0.15);
            border-color: #818CF8;
        }}
        .stButton > button[kind="tertiary"] {{
            color: #94A3B8;
        }}
        .stButton > button[kind="tertiary"]:hover {{
            background: rgba(255, 255, 255, 0.05);
            color: #E2E8F0;
        }}
        .app-header {{
            border-bottom-color: #334155;
        }}
        hr {{
            border-color: #334155;
        }}
        [data-testid="stExpander"] summary {{
            color: #94A3B8;
        }}
        .todo-item:hover {{
            background: rgba(255, 255, 255, 0.03);
        }}
        .decision-item {{
            background: rgba(99, 102, 241, 0.1);
        }}
        .decision-item:hover {{
            background: rgba(99, 102, 241, 0.18);
        }}
        .transcript-line:hover {{
            background: rgba(255, 255, 255, 0.03);
        }}
        .transcript-ts {{
            background: rgba(255, 255, 255, 0.06);
            color: #64748B;
        }}
        .error-card {{
            background: rgba(239, 68, 68, 0.1);
            border-color: rgba(239, 68, 68, 0.3);
        }}
        .empty-title {{
            color: #F1F5F9;
        }}
        [data-testid="stSuccess"] div,
        [data-testid="stInfo"] div,
        [data-testid="stWarning"] div,
        [data-testid="stError"] div {{
            background: rgba(0,0,0,0.2) !important;
        }}
    }}

    /* ==================================================================
       COLLAPSIBLE TEXT
       ================================================================== */
    .text-collapsed {{
        max-height: 320px;
        overflow: hidden;
        position: relative;
    }}
    .text-collapsed::after {{
        content: '';
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        height: 80px;
        background: linear-gradient(transparent, #F1F5F9);
        pointer-events: none;
    }}
    @media (prefers-color-scheme: dark) {{
        .text-collapsed::after {{
            background: linear-gradient(transparent, #1E293B);
        }}
    }}

    /* ==================================================================
       TABLE HORIZONTAL SCROLL
       ================================================================== */
    .stDataFrame {{
        overflow-x: auto;
        max-width: 100%;
    }}
    .stDataFrame table {{
        width: 100%;
        min-width: 400px;
    }}
    </style>
    """,
        unsafe_allow_html=True,
    )
