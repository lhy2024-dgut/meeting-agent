"""术语词表管理服务

每场会议的词表存储在 storage/terms/{meeting_id}.json
结构：{"terms": ["词条1", ...], "updated_at": "ISO8601"}

Token 估算规则（简化）：
  - 中文字符：每字约 1.5 token
  - 英文/数字：每词约 1 token
  上限 200 token，超出时按插入顺序截断。
"""

import json
from datetime import datetime
from pathlib import Path

import config
from logger import get_logger

logger = get_logger(__name__)

TERMS_DIR = config.STORAGE_DIR / "terms"
TERMS_DIR.mkdir(exist_ok=True)

MAX_TOKENS = 200


# ── Token 估算 ────────────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """粗略估算文本 token 数（中文按字计，其余按词计）"""
    import re
    zh_chars = len(re.findall(r"[一-鿿]", text))
    rest = len(re.findall(r"[a-zA-Z0-9]+", text))
    return int(zh_chars * 1.5) + rest


def truncate_terms(terms: list[str], max_tokens: int = MAX_TOKENS) -> tuple[list[str], bool]:
    """按优先级（插入顺序）截断术语列表，返回 (截断后列表, 是否已截断)"""
    kept, total = [], 0
    for t in terms:
        tok = _estimate_tokens(t) + 1  # +1 for separator
        if total + tok > max_tokens:
            return kept, True
        kept.append(t)
        total += tok
    return kept, False


# ── 持久化 ────────────────────────────────────────────────────────────────────

def save_terms(meeting_id: int, terms: list[str]) -> None:
    path = TERMS_DIR / f"{meeting_id}.json"
    path.write_text(
        json.dumps({"terms": terms, "updated_at": datetime.now().isoformat()},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("已保存会议 %s 词表（%d 条）", meeting_id, len(terms))


def load_terms(meeting_id: int) -> list[str]:
    path = TERMS_DIR / f"{meeting_id}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("terms", [])
    except Exception as e:
        logger.warning("加载会议 %s 词表失败: %s", meeting_id, e)
        return []


# ── Prompt 构建 ───────────────────────────────────────────────────────────────

def build_whisper_prompt(terms: list[str], base_prompt: str = "") -> str:
    """构建 faster-whisper initial_prompt，注入术语"""
    if not base_prompt:
        base_prompt = "以下是普通话会议录音，请使用简体中文输出。"
    kept, truncated = truncate_terms(terms)
    if truncated:
        logger.warning("术语列表超出 token 限制，已截断至 %d 条", len(kept))
    if not kept:
        return base_prompt
    terms_str = "，".join(kept)
    return f"{base_prompt}本次会议涉及以下专有术语，请优先识别：{terms_str}。"


def build_sensevoice_hotword(terms: list[str]) -> str | None:
    """构建 SenseVoice hotword 字符串（空格分隔）"""
    kept, truncated = truncate_terms(terms)
    if truncated:
        logger.warning("术语列表超出 token 限制，已截断至 %d 条", len(kept))
    if not kept:
        return None
    return " ".join(kept)
