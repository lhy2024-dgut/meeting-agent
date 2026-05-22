# -*- coding: utf-8 -*-
"""简单文本分块器 — 替代 langchain_text_splitters，避免触发 transformers/onnxruntime 崩溃"""

import re


class SimpleTextSplitter:
    """基于分隔符递归分割 + 长度合并的中文友好分块器"""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        # 按优先级从高到低排列：段落 → 换行 → 中文标点 → 英文标点 → 空格 → 字符
        self._separators = [
            r"\n\n",
            r"\n",
            r"[。！？；]",
            r"[\.!\?;]",
            r"\s+",
        ]

    def split_text(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []
        return self._split_recursive(text.strip(), 0)

    def _split_recursive(self, text: str, depth: int) -> list[str]:
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        if depth >= len(self._separators):
            # 最后手段：按字符切
            return self._merge_chunks(list(text))

        sep = self._separators[depth]
        parts = re.split(f"({sep})", text)

        # 合并分隔符到前一部分
        merged = []
        buffer = ""
        for part in parts:
            if re.fullmatch(sep, part):
                buffer += part
            else:
                merged.append(buffer + part)
                buffer = ""

        if buffer:
            if merged:
                merged[-1] += buffer
            else:
                merged.append(buffer)

        # 对每个部分继续递归或合并
        result = []
        for part in merged:
            part = part.strip()
            if not part:
                continue
            if len(part) <= self.chunk_size:
                result.append(part)
            else:
                result.extend(self._split_recursive(part, depth + 1))

        return self._merge_chunks(result)

    def _merge_chunks(self, chunks: list[str]) -> list[str]:
        """合并过小的 chunk，并处理 overlap"""
        if not chunks:
            return []

        merged = []
        current = ""

        for chunk in chunks:
            if not current:
                current = chunk
            elif len(current) + len(chunk) <= self.chunk_size:
                current += chunk
            else:
                merged.append(current)
                if self.chunk_overlap > 0 and len(current) > self.chunk_overlap:
                    combined = current[-self.chunk_overlap:] + chunk
                    current = combined[:self.chunk_size]
                else:
                    current = chunk

        if current:
            merged.append(current)

        return merged
