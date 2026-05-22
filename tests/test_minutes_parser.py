import pytest

from chains.minutes_chain import MinutesOutputParser


class TestMinutesOutputParser:

    def test_parse_all_sections(self):
        text = (
            "===ACTION_ITEMS===\n- [ ] 任务1 | 张三 | 2024-01-15\n"
            "===RESOLUTIONS===\n1. 决议1\n2. 决议2\n"
            "===MINUTES===\n会议纪要内容"
        )
        action, res, minutes = MinutesOutputParser().parse(text)
        assert "任务1" in action
        assert "决议1" in res
        assert "决议2" in res
        assert "会议纪要内容" in minutes

    def test_parse_partial_only_minutes(self):
        text = "===MINUTES===\n只有纪要内容"
        action, res, minutes = MinutesOutputParser().parse(text)
        assert "只有纪要内容" in minutes

    def test_parse_no_format_fallback(self):
        text = "这是完全没有格式的文本"
        action, res, minutes = MinutesOutputParser().parse(text)
        assert "请查看会议纪要" in action
        assert text in minutes

    def test_parse_empty(self):
        action, res, minutes = MinutesOutputParser().parse("")
        assert "请查看会议纪要" in action

    def test_parse_alternative_case(self):
        text = (
            "===action_items===\n- [ ] task\n"
            "===resolutions===\n1. resolution\n"
            "===minutes===\ncontent"
        )
        action, res, minutes = MinutesOutputParser().parse(text)
        assert "task" in action
        assert "resolution" in res
        assert "content" in minutes
