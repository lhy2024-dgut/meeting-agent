import pytest

from engines.asr_engine import ASREngine


class TestClassifyDuration:

    def test_short(self):
        assert ASREngine.classify_duration(120) == "short"

    def test_medium(self):
        assert ASREngine.classify_duration(600) == "medium"

    def test_long(self):
        assert ASREngine.classify_duration(3600) == "long"

    def test_boundary_short_medium(self):
        assert ASREngine.classify_duration(299) == "short"
        assert ASREngine.classify_duration(300) == "medium"

    def test_boundary_medium_long(self):
        assert ASREngine.classify_duration(1799) == "medium"
        assert ASREngine.classify_duration(1800) == "long"
