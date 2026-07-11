"""术语词表存储模块

每场会议的词表独立存为 storage/terms/{meeting_id}.json。
提供 save / load / delete 三个操作。
"""

import json
from datetime import datetime
from pathlib import Path

from logger import get_logger

logger = get_logger(__name__)

TERMS_DIR = Path("storage/terms")


def _ensure_dir():
    TERMS_DIR.mkdir(parents=True, exist_ok=True)


def _path(meeting_id: int) -> Path:
    return TERMS_DIR / f"{meeting_id}.json"


def save_terms(meeting_id: int, terms: list[str]) -> dict:
    """保存词表，覆盖写入"""
    _ensure_dir()
    data = {
        "terms": [t.strip() for t in terms if t.strip()],
        "updated_at": datetime.now().isoformat(),
    }
    with open(_path(meeting_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("词表已保存: meeting_id=%s, 共 %d 条", meeting_id, len(data["terms"]))
    return data


def load_terms(meeting_id: int) -> list[str]:
    """加载词表，返回词条列表"""
    p = _path(meeting_id)
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("terms", [])
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("词表文件解析失败: %s", e)
        return []


def delete_terms(meeting_id: int) -> None:
    """删除词表文件"""
    p = _path(meeting_id)
    if p.exists():
        p.unlink()
        logger.info("词表已删除: meeting_id=%s", meeting_id)
