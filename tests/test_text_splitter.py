import pytest

from rag.text_splitter import SimpleTextSplitter


class TestSimpleTextSplitter:

    def test_short_text_no_split(self):
        splitter = SimpleTextSplitter(chunk_size=512)
        assert len(splitter.split_text("短文本")) == 1

    def test_empty_text(self):
        assert SimpleTextSplitter().split_text("") == []
        assert SimpleTextSplitter().split_text("   ") == []

    def test_all_chunks_within_limit(self):
        splitter = SimpleTextSplitter(chunk_size=100, chunk_overlap=20)
        long_text = "第一段内容。第二段内容。第三段内容。第四段内容。" * 20
        chunks = splitter.split_text(long_text)
        assert len(chunks) > 1
        assert all(len(c) <= 100 for c in chunks)

    def test_chinese_paragraph(self):
        splitter = SimpleTextSplitter(chunk_size=20, chunk_overlap=5)
        text = "今天讨论了项目进度。下一步需要确认排期。还需要分配资源。"
        chunks = splitter.split_text(text)
        assert len(chunks) >= 2
        assert all(len(c) <= 20 for c in chunks)

    def test_single_long_word(self):
        splitter = SimpleTextSplitter(chunk_size=10, chunk_overlap=3)
        text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        chunks = splitter.split_text(text)
        assert len(chunks) >= 2
        assert all(len(c) <= 10 for c in chunks)
