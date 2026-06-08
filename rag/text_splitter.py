# -*- coding: utf-8 -*-
"""文本分块器集合

SimpleTextSplitter      — 固定 512 字递归切分（现有策略）
WhisperSegmentSplitter  — faster-whisper segments 合并至目标字数
SenseVoiceSegmentSplitter — SenseVoiceSmall segments 合并至目标字数
SemanticTextSplitter    — 基于 embedding 余弦相似度的语义边界切分
"""

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


# ── faster-whisper Segment 合并分块器 ────────────────────────────────────────

class WhisperSegmentSplitter:
    """将 faster-whisper 输出的 segments 按目标字数合并成 chunk。

    每个 segment 格式：{"id": int, "text": str, "start": float, "end": float, ...}
    返回文本列表，用于 rebuild_meeting_index 的 transcript chunk 类型。
    保持独立实现，便于后续选型后删除。
    """

    def __init__(self, target_chars: int = 300):
        self.target_chars = target_chars

    def split_segments(self, segments: list[dict]) -> list[str]:
        """合并 segments 直到达到目标字数，返回文本列表"""
        if not segments:
            return []
        chunks, buf = [], ""
        for seg in segments:
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            buf += text
            if len(buf) >= self.target_chars:
                chunks.append(buf)
                buf = ""
        if buf:
            chunks.append(buf)
        return chunks


# ── SenseVoiceSmall Segment 合并分块器 ───────────────────────────────────────

class SenseVoiceSegmentSplitter:
    """将 SenseVoiceSmall 输出的 segments 按目标字数合并成 chunk。

    segment 格式与 WhisperSegmentSplitter 相同（已在 sense_voice_engine 统一）。
    保持独立实现，便于后续选型后删除。
    """

    def __init__(self, target_chars: int = 300):
        self.target_chars = target_chars

    def split_segments(self, segments: list[dict]) -> list[str]:
        """合并 segments 直到达到目标字数，返回文本列表"""
        if not segments:
            return []
        chunks, buf = [], ""
        for seg in segments:
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            buf += text
            if len(buf) >= self.target_chars:
                chunks.append(buf)
                buf = ""
        if buf:
            chunks.append(buf)
        return chunks


# ── 语义切分器 ────────────────────────────────────────────────────────────────

class SemanticTextSplitter:
    """基于相邻句子 embedding 余弦相似度的语义边界切分。

    实现思路（参考华侨大学 RAPTOR 论文，2026）：
      1. 按中文/英文标点将文本切成句子序列
      2. 对每相邻两句计算余弦相似度 sim(i) = cos(embed(Si), embed(Si+1))
      3. 当 sim(i) 低于自适应阈值时判定话题切换，在此处断开
      4. 将语义连贯的句子聚合成 chunk；过短的 chunk 与相邻合并
    """

    def __init__(self, embeddings, threshold: float = 0.75,
                 min_chunk: int = 80, max_chunk: int = 600):
        self.embeddings = embeddings
        self.threshold = threshold   # 相似度低于此值视为话题切换
        self.min_chunk = min_chunk   # 过短的 chunk 向后合并
        self.max_chunk = max_chunk   # 过长则强制截断（防止单句过长异常）

    # ── 公共接口（与 SimpleTextSplitter 兼容）────────────────────────────────

    def split_text(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []
        sentences = self._split_sentences(text)
        if len(sentences) <= 2:
            return [text.strip()] if text.strip() else []

        # 批量计算 embedding，避免逐句调用
        vecs = self.embeddings.embed_documents(sentences)
        sims = [self._cosine(vecs[i], vecs[i + 1]) for i in range(len(vecs) - 1)]

        # 自适应阈值：均值 - 0.5 * 标准差（使断点集中在相对低谷处）
        if len(sims) > 1:
            mean = sum(sims) / len(sims)
            std = (sum((s - mean) ** 2 for s in sims) / len(sims)) ** 0.5
            adaptive_threshold = mean - 0.5 * std
        else:
            adaptive_threshold = self.threshold
        cutoff = min(self.threshold, adaptive_threshold)

        # 确定切分点（相似度低于阈值 → 新 chunk 起始）
        breakpoints = {i + 1 for i, s in enumerate(sims) if s < cutoff}

        # 聚合句子
        raw_chunks, buf = [], []
        for i, sent in enumerate(sentences):
            if i in breakpoints and buf:
                raw_chunks.append("".join(buf))
                buf = []
            buf.append(sent)
        if buf:
            raw_chunks.append("".join(buf))

        return self._post_process(raw_chunks)

    # ── 私有方法 ──────────────────────────────────────────────────────────────

    def _split_sentences(self, text: str) -> list[str]:
        """按中英文句末标点切句，保留标点"""
        parts = re.split(r"(?<=[。！？；\.\!\?;])", text)
        return [p for p in parts if p.strip()]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    def _post_process(self, chunks: list[str]) -> list[str]:
        """合并过短 chunk，截断过长 chunk"""
        result = []
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            if result and len(result[-1]) < self.min_chunk:
                result[-1] += chunk
            elif len(chunk) > self.max_chunk:
                # 超长则按 max_chunk 强制截断
                for i in range(0, len(chunk), self.max_chunk):
                    result.append(chunk[i:i + self.max_chunk])
            else:
                result.append(chunk)
        return result
