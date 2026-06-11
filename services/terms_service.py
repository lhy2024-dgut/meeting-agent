"""术语词表管理服务。"""

import json
from datetime import datetime

import config
from logger import get_logger

logger = get_logger(__name__)

TERMS_DIR = config.STORAGE_DIR / "terms"
TERMS_DIR.mkdir(exist_ok=True)

MAX_TOKENS = 200


def _estimate_tokens(text: str) -> int:
    """粗略估算文本 token 数。"""
    import re

    zh_chars = len(re.findall(r"[一-鿿]", text))
    rest = len(re.findall(r"[a-zA-Z0-9]+", text))
    return int(zh_chars * 1.5) + rest


def truncate_terms(terms: list[str], max_tokens: int = MAX_TOKENS) -> tuple[list[str], bool]:
    """按输入顺序截断术语词表，返回 (截断后列表, 是否截断)。"""
    kept, total = [], 0
    for term in terms:
        token_count = _estimate_tokens(term) + 1
        if total + token_count > max_tokens:
            return kept, True
        kept.append(term)
        total += token_count
    return kept, False


def save_terms(meeting_id: int, terms: list[str]) -> None:
    path = TERMS_DIR / f"{int(meeting_id)}.json"
    normalized = [term.strip() for term in terms if term and term.strip()]
    path.write_text(
        json.dumps(
            {"terms": normalized, "updated_at": datetime.now().isoformat()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("已保存会议 %s 术语词表（%d 条）", meeting_id, len(normalized))


def load_terms(meeting_id: int) -> list[str]:
    path = TERMS_DIR / f"{int(meeting_id)}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("terms", [])
    except Exception as exc:
        logger.warning("加载会议 %s 术语词表失败: %s", meeting_id, exc)
        return []


def build_whisper_prompt(terms: list[str], base_prompt: str = "") -> str:
    """构建 faster-whisper initial_prompt。"""
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
    """构建 SenseVoice hotword 字符串。"""
    kept, truncated = truncate_terms(terms)
    if truncated:
        logger.warning("术语列表超出 token 限制，已截断至 %d 条", len(kept))
    if not kept:
        return None
    return " ".join(kept)
