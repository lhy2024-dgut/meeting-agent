import hashlib
import re
from collections import OrderedDict

from langchain_core.output_parsers import BaseOutputParser

from engines.llm import get_llm, OllamaLLMError
from logger import get_logger
from prompts.templates import MINUTES_PROMPT

logger = get_logger(__name__)


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
        if not any([action, resolutions, minutes]):
            return "请查看会议纪要", "请查看会议纪要", text or ""
        return action, resolutions, minutes

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
            except OllamaLLMError:
                if attempt < self.MAX_RETRY:
                    logger.warning("LLM 调用失败，重试 %s/%s", attempt + 1, self.MAX_RETRY)
                    continue
                raise
            action, resolutions, minutes = self.parser.parse(raw)
            if minutes.strip() and minutes.strip() != "请查看会议纪要":
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
            action = "本次会议未明确待办事项。"
            resolutions = "本次会议未明确决议。"

        result = (action, resolutions, minutes)
        self._cache[key] = result
        if len(self._cache) > self._max_cache:
            self._cache.popitem(last=False)
        return result
