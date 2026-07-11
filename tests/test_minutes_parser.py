import pytest

from chains.minutes_chain import (
    MinutesOutputParser,
    PLACEHOLDER_NO_ACTION,
    PLACEHOLDER_NO_RESOLUTION,
)


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
        # action_items 和 resolutions 应 fallback 到占位符
        assert action == PLACEHOLDER_NO_ACTION
        assert res == PLACEHOLDER_NO_RESOLUTION

    def test_parse_no_format_fallback(self):
        text = "这是完全没有格式的文本"
        action, res, minutes = MinutesOutputParser().parse(text)
        assert PLACEHOLDER_NO_ACTION in action
        assert text in minutes

    def test_parse_empty(self):
        action, res, minutes = MinutesOutputParser().parse("")
        assert PLACEHOLDER_NO_ACTION in action

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

    # ── Fallback extraction tests ──

    def test_extract_action_items_from_minutes_block(self):
        """当 ===ACTION_ITEMS=== 块为空时，从 MINUTES 块中提取 - [ ] 格式"""
        text = (
            "===ACTION_ITEMS===\n本次会议未明确待办事项。\n"
            "===RESOLUTIONS===\n1. 确认方案A\n"
            "===MINUTES===\n"
            "# 会议纪要\n\n"
            "## 讨论要点\n- 讨论了方案A\n\n"
            "## 待办任务\n"
            "- [ ] 完成报告 | 张三 | 6月15日\n"
            "- [ ] 采购设备 | 李四\n"
        )
        action, res, minutes = MinutesOutputParser().parse(text)
        assert "完成报告" in action
        assert "采购设备" in action
        assert "确认方案A" in res

    def test_extract_action_items_from_full_text(self):
        """当 MINUTES 块也没有时，从全文范围提取 - [ ]"""
        text = (
            "一些前面的话\n"
            "- [ ] 任务A | 负责人\n"
            "- [x] 已完成任务\n"
            "中间内容\n"
            "- [ ] 任务B\n"
        )
        action, res, minutes = MinutesOutputParser().parse(text)
        assert "任务A" in action
        assert "任务B" in action

    def test_extract_resolutions_from_minutes_block(self):
        """从 MINUTES 块中提取数字编号格式的决议"""
        text = (
            "===ACTION_ITEMS===\n- [ ] 任务1\n"
            "===RESOLUTIONS===\n本次会议未明确决议。\n"
            "===MINUTES===\n"
            "# 会议纪要\n\n"
            "## 决议事项\n"
            "1. 通过预算方案\n"
            "2. 确定下月启动\n"
        )
        action, res, minutes = MinutesOutputParser().parse(text)
        assert "通过预算方案" in res
        assert "确定下月启动" in res
