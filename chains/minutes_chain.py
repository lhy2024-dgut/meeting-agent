import hashlib
import re
from collections import OrderedDict

from langchain_core.output_parsers import BaseOutputParser

from engines.llm import get_llm, OllamaLLMError
from logger import get_logger
from prompts.templates import MINUTES_PROMPT

logger = get_logger(__name__)

# ── 统一占位符常量 ─────────────────────────────────────────
PLACEHOLDER_NO_ACTION = "本次会议未明确待办事项。"
PLACEHOLDER_NO_RESOLUTION = "本次会议未明确决议。"
PLACEHOLDER_LEGACY_FALLBACK = "请查看会议纪要"
PLACEHOLDER_ALL_EMPTY = {PLACEHOLDER_NO_ACTION, PLACEHOLDER_NO_RESOLUTION, PLACEHOLDER_LEGACY_FALLBACK}


class MinutesOutputParser(BaseOutputParser):
    """解析三段式纪要输出 ===ACTION_ITEMS=== / ===RESOLUTIONS=== / ===MINUTES==="""

    def parse(self, text):
        def get_section(name):
            pattern = rf"===\s*{name}\s*===\s*(.*?)(?===\s*\w+\s*===|$)"
            match = re.search(pattern, text or "", re.DOTALL | re.IGNORECASE)
            return match.group(1).strip() if match else ""

        action = get_section("ACTION_ITEMS")
        resolutions = get_section("RESOLUTIONS")
        minutes = get_section("MINUTES")

        # ── 没有任何 ===SECTION=== 标记 → 尝试从全文 fallback 提取 ──
        if not any([action, resolutions, minutes]):
            extracted_action = self._extract_action_items_from_text(text)
            extracted_res = self._extract_resolutions_from_text(text)
            return (
                extracted_action or PLACEHOLDER_NO_ACTION,
                extracted_res or PLACEHOLDER_NO_RESOLUTION,
                text or "",
            )

        # ── 有标记但 section 为占位符 → fallback 从全文中提取 ──
        if not action.strip() or action.strip() in PLACEHOLDER_ALL_EMPTY:
            extracted = self._extract_action_items_from_text(text)
            if extracted:
                action = extracted

        if not resolutions.strip() or resolutions.strip() in PLACEHOLDER_ALL_EMPTY:
            extracted = self._extract_resolutions_from_text(text)
            if extracted:
                resolutions = extracted

        # 最终保底
        if not action.strip() or action.strip() in PLACEHOLDER_ALL_EMPTY:
            action = PLACEHOLDER_NO_ACTION
        if not resolutions.strip() or resolutions.strip() in PLACEHOLDER_ALL_EMPTY:
            resolutions = PLACEHOLDER_NO_RESOLUTION

        return action, resolutions, minutes

    @staticmethod
    def _extract_action_items_from_text(text: str) -> str:
        """从全文（优先在 MINUTES 块中）提取 - [ ] 格式的待办事项"""
        # 策略 1：在 ===MINUTES=== 块中查找 - [ ] 列表
        minutes_block = re.search(
            r"===\s*MINUTES\s*===\s*(.*?)$", text or "", re.DOTALL | re.IGNORECASE
        )
        candidates = [minutes_block.group(1)] if minutes_block else [text]

        for block in candidates:
            lines = block.split("\n")
            todo_lines = []
            in_todo_section = False
            for line in lines:
                stripped = line.strip()
                if re.match(r"^- \[.\] ", stripped) or re.match(r"^- \[ \] ", stripped):
                    todo_lines.append(stripped)
                    in_todo_section = True
                elif in_todo_section and stripped.startswith("- ") and not stripped.startswith("- ["):
                    todo_lines.append(stripped)
                elif in_todo_section and not stripped:
                    continue  # 空行跳过
                elif in_todo_section:
                    break  # 非列表行 → 列表结束

            if todo_lines:
                return "\n".join(todo_lines)

        # 策略 2：全文范围查找 - [ ] 格式
        all_todos = re.findall(r"^- \[[ x]\] .+", text or "", re.MULTILINE)
        if all_todos:
            return "\n".join(all_todos)
        return ""

    @staticmethod
    def _extract_resolutions_from_text(text: str) -> str:
        """从全文（优先在 MINUTES 块中）提取决议内容"""
        minutes_block = re.search(
            r"===\s*MINUTES\s*===\s*(.*?)$", text or "", re.DOTALL | re.IGNORECASE
        )
        candidates = [minutes_block.group(1)] if minutes_block else [text]

        for block in candidates:
            lines = block.split("\n")
            res_lines = []
            in_res_section = False
            for line in lines:
                stripped = line.strip()
                if re.match(r"^\d+[\.\)、]\s+", stripped) or stripped.startswith("- 决议"):
                    res_lines.append(stripped)
                    in_res_section = True
                elif in_res_section and not stripped:
                    continue
                elif in_res_section:
                    break
            if res_lines:
                return "\n".join(res_lines)

        all_res = re.findall(r"^\d+[\.\)、]\s+.*$", text or "", re.MULTILINE)
        if all_res:
            return "\n".join(all_res)
        return ""

    @property
    def _type(self):
        return "minutes_output_parser"


class MinutesChain:
    """会议纪要生成链，基于 LCEL，含 LRU 缓存 + 解析失败 retry"""

    MAX_RETRY = 2
    MAX_TRANSCRIPT_LEN = 8000
    FALLBACK_TRANSCRIPT_LEN = 4000

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.1)
        self.chain = MINUTES_PROMPT | self.llm
        self.parser = MinutesOutputParser()
        self._cache = OrderedDict()
        self._max_cache = 128

    def run(self, transcript, title="", date=""):
        transcript = transcript or ""
        key = hashlib.md5(transcript.encode()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        if len(transcript) > self.MAX_TRANSCRIPT_LEN:
            logger.warning(
                "转录文本过长 (%d 字符)，截断至 %d，可能丢失会议内容",
                len(transcript), self.MAX_TRANSCRIPT_LEN,
            )

        params = {
            "transcript": transcript[:self.MAX_TRANSCRIPT_LEN],
            "title": title,
            "date": date,
        }

        for attempt in range(self.MAX_RETRY + 1):
            try:
                raw = self.chain.invoke(params)
                raw_text = raw.content if hasattr(raw, 'content') else str(raw)
            except OllamaLLMError:
                if attempt < self.MAX_RETRY:
                    logger.warning("LLM 调用失败，重试 %s/%s", attempt + 1, self.MAX_RETRY)
                    continue
                raise
            action, resolutions, minutes = self.parser.parse(raw_text)
            if minutes.strip() and minutes.strip() not in PLACEHOLDER_ALL_EMPTY:
                break
            if attempt < self.MAX_RETRY:
                logger.warning("纪要解析不完整，重试 %s/%s", attempt + 1, self.MAX_RETRY)
        else:
            # 全部失败：用原文做备用纪要
            if len(transcript) > self.FALLBACK_TRANSCRIPT_LEN:
                logger.warning(
                    "纪要生成全部失败，回退原文截断 %d -> %d 字符",
                    len(transcript), self.FALLBACK_TRANSCRIPT_LEN,
                )
            minutes = transcript[:self.FALLBACK_TRANSCRIPT_LEN]
            action = PLACEHOLDER_NO_ACTION
            resolutions = PLACEHOLDER_NO_RESOLUTION

        result = (action, resolutions, minutes)
        self._cache[key] = result
        if len(self._cache) > self._max_cache:
            self._cache.popitem(last=False)
        return result
