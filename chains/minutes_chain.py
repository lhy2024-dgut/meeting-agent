import hashlib
import json
import re
from collections import OrderedDict

from langchain_core.output_parsers import BaseOutputParser, StrOutputParser

from engines.llm import get_llm, OllamaLLMError
from logger import get_logger
from prompts.templates import PromptTemplateLoader

logger = get_logger(__name__)

# ── 统一占位符常量 ─────────────────────────────────────────
PLACEHOLDER_NO_ACTION = "本次会议未明确待办事项。"
PLACEHOLDER_NO_RESOLUTION = "本次会议未明确决议。"
PLACEHOLDER_LEGACY_FALLBACK = "请查看会议纪要"
PLACEHOLDER_ALL_EMPTY = {PLACEHOLDER_NO_ACTION, PLACEHOLDER_NO_RESOLUTION, PLACEHOLDER_LEGACY_FALLBACK}


_CHINESE_ORDINALS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def _add_heading_ordinals(text: str) -> str:
    """为 ## 二级标题加汉字序号（一、二、三、…），为 ### 三级标题加阿拉伯序号（1. 2. 3. …）。
    遇到 # 一级标题时重置 ## 计数；遇到 ## 时重置 ### 计数。已有序号则跳过（幂等）。
    """
    lines = text.split('\n')
    h2_count = 0
    h3_count = 0
    result = []
    for line in lines:
        if line.startswith('# ') and not line.startswith('## '):
            h2_count = 0
            h3_count = 0
        elif line.startswith('## ') and not line.startswith('### '):
            content = line[3:]
            if not re.match(r'^[一二三四五六七八九十]+、', content):
                h2_count += 1
                ordinal = _CHINESE_ORDINALS[h2_count - 1] if h2_count <= len(_CHINESE_ORDINALS) else str(h2_count)
                line = f'## {ordinal}、{content}'
            h3_count = 0
        elif line.startswith('### '):
            content = line[4:]
            if not re.match(r'^\d+\.', content):
                h3_count += 1
                line = f'### {h3_count}. {content}'
        result.append(line)
    return '\n'.join(result)


def _repair_json_newlines(json_str: str) -> str:
    """Escape literal newlines/tabs that appear inside JSON string values.

    LLMs sometimes emit raw line-breaks inside a JSON string instead of the
    required \\n escape sequence.  We walk the JSON character-by-character,
    track whether we are inside a quoted string, and fix any bare control
    characters we find there.
    """
    result = []
    in_string = False
    escape_next = False
    for ch in json_str:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == '\n':
                result.append('\\n')
                continue
            if ch == '\r':
                result.append('\\r')
                continue
            if ch == '\t':
                result.append('\\t')
                continue
        result.append(ch)
    return ''.join(result)


def _try_parse_json(text: str) -> dict | None:
    """从 LLM 输出中提取 JSON 对象（新格式）。

    兼容 LLM 在 JSON 前后附加说明文字、markdown 代码块包裹，以及字符串值内含
    原始换行符（LLM 未转义为 \\n）的情况。
    返回 dict 或 None（解析失败时）。
    """
    text = text.strip()
    # 去掉 ```json ... ``` 代码块标记
    text = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    json_str = text[start : end + 1]

    # 第一次尝试：直接解析
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # 第二次尝试：修复字符串值内的裸换行符后再解析
    try:
        return json.loads(_repair_json_newlines(json_str))
    except json.JSONDecodeError:
        return None


class MinutesOutputParser(BaseOutputParser):
    """解析旧三段式纪要输出 ===ACTION_ITEMS=== / ===RESOLUTIONS=== / ===MINUTES===

    保持向后兼容；新 JSON 格式由 MinutesChain.run() 中的 _try_parse_json() 优先处理。
    """

    def parse(self, text: str):
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
    """会议纪要生成链，含 LRU 缓存 + 解析失败 retry + 场景化提示词支持"""

    MAX_RETRY = 2
    MAX_TRANSCRIPT_LEN = 8000
    FALLBACK_TRANSCRIPT_LEN = 4000

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.1)
        self.parser = MinutesOutputParser()
        self._cache = OrderedDict()
        self._max_cache = 128

    def run(self, transcript, title="", date="", scene="通用会议", custom_headings=None):
        """生成会议纪要。

        Args:
            transcript: 会议转录文本。
            title: 会议标题。
            date: 会议日期字符串。
            scene: 场景模板名称（如 "学术组会"），默认 "通用会议"。
            custom_headings: 用户自定义一级标题列表，非空时覆盖场景默认标题。

        Returns:
            (action_items, resolutions, minutes) 三元组，minutes 为完整纪要文档。
        """
        transcript = transcript or ""
        custom_headings = custom_headings or []

        cache_input = f"{transcript}|{scene}|{','.join(custom_headings)}"
        key = hashlib.md5(cache_input.encode()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        if len(transcript) > self.MAX_TRANSCRIPT_LEN:
            logger.warning(
                "转录文本过长 (%d 字符)，截断至 %d，可能丢失会议内容",
                len(transcript),
                self.MAX_TRANSCRIPT_LEN,
            )

        prompt = PromptTemplateLoader.load(scene, custom_headings if custom_headings else None)
        chain = prompt | self.llm | StrOutputParser()

        params = {
            "transcript": transcript[: self.MAX_TRANSCRIPT_LEN],
            "title": title,
            "date": date,
        }

        action_items = ""
        resolutions = ""
        minutes = ""

        for attempt in range(self.MAX_RETRY + 1):
            try:
                raw = chain.invoke(params)
                raw_text = raw.content if hasattr(raw, 'content') else str(raw)
            except OllamaLLMError:
                if attempt < self.MAX_RETRY:
                    logger.warning("LLM 调用失败，重试 %s/%s", attempt + 1, self.MAX_RETRY)
                    continue
                raise
            # 优先尝试新 JSON 格式（使用 raw_text 兼容 AIMessage）
            parsed = _try_parse_json(raw_text)
            if parsed:
                topic = parsed.get("topic", "")
                body = parsed.get("minutes", "")
                action_items = parsed.get("todos", "")
                resolutions = parsed.get("decisions", "")
                # 组装完整纪要文档（含标题、日期、主题），再统一加序号
                header = f"# 会议纪要：{title}\n**日期**：{date}\n\n" if title else ""
                topic_section = f"## 会议主题\n{topic}\n\n" if topic else ""
                minutes = _add_heading_ordinals(header + topic_section + body)
            else:
                # 回退到旧三段式格式
                logger.debug("JSON 解析失败，回退至 ===SECTION=== 解析器")
                action_items, resolutions, minutes = self.parser.parse(raw_text)

            if minutes.strip() and minutes.strip() != "请查看会议纪要":
                break
            if attempt < self.MAX_RETRY:
                logger.warning("纪要解析不完整，重试 %s/%s", attempt + 1, self.MAX_RETRY)
        else:
            # 全部重试失败：用原文截断作为备用纪要
            if len(transcript) > self.FALLBACK_TRANSCRIPT_LEN:
                logger.warning(
                    "纪要生成全部失败，回退原文截断 %d -> %d 字符",
                    len(transcript),
                    self.FALLBACK_TRANSCRIPT_LEN,
                )
            minutes = transcript[: self.FALLBACK_TRANSCRIPT_LEN]
            action_items = "本次会议未明确待办事项。"
            resolutions = "本次会议未明确决议。"

        result = (action_items, resolutions, minutes)
        self._cache[key] = result
        if len(self._cache) > self._max_cache:
            self._cache.popitem(last=False)
        return result
