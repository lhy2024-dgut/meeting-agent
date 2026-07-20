from services.meeting_service import MeetingService


def test_generate_summary_is_derived_without_llm(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("summary generation should not call the LLM")

    monkeypatch.setattr("services.meeting_service.get_logger", fail_if_called, raising=False)

    minutes = (
        "# 会议纪要：产品评审\n"
        "**日期**：2026-07-20 10:00\n\n"
        "## 会议主题\n"
        "耳机产品评审\n\n"
        "## 一、目标用户\n"
        "- 面向年轻用户\n"
        "- 强化降噪体验\n"
    )

    short_summary, project_name = MeetingService._generate_summary(
        "会议讨论了目标用户和降噪体验。",
        minutes,
        title="产品评审",
    )

    assert project_name == "产品评审"
    assert "耳机产品评审" in short_summary
    assert "目标用户" in short_summary
