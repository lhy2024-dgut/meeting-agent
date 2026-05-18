import hashlib
import re

from langchain_core.output_parsers import BaseOutputParser

import config
from prompts.templates import MINUTES_PROMPT


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
    """会议纪要生成链，基于 LCEL"""

    def __init__(self):
        self.llm = config.get_llm(temperature=0.1)
        self.chain = MINUTES_PROMPT | self.llm | MinutesOutputParser()
        self._cache = {}

    def run(self, transcript, title="", date=""):
        key = hashlib.md5((transcript or "").encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]

        result = self.chain.invoke({
            "transcript": (transcript or "")[:8000],
            "title": title,
            "date": date,
        })
        self._cache[key] = result
        return result
