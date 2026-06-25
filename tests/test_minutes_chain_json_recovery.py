from chains.minutes_chain import (
    MinutesChain,
    _has_meaningful_minutes_content,
    normalize_structured_minutes_output,
    _try_parse_json,
)
from langchain_core.runnables import RunnableLambda
from prompts.templates import PromptTemplateLoader


def test_try_parse_json_recovers_truncated_structured_minutes():
    raw = (
        '{"topic": "耳机产品推广", '
        '"minutes": "## 目标用户\\n- 面向年轻人", '
        '"decisions": "## 渠道决策\\n- 先做中腰部主播", '
        '"todos": "## 执行任务\\n- 【市场部】提交预算\\n- 【设计组】提交渲染图'
    )

    parsed = _try_parse_json(raw)

    assert parsed is not None
    assert parsed["topic"] == "耳机产品推广"
    assert "目标用户" in parsed["minutes"]
    assert "渠道决策" in parsed["decisions"]
    assert "提交预算" in parsed["todos"]
    assert "提交渲染图" in parsed["todos"]


def test_normalize_structured_minutes_output_formats_document_and_sections():
    raw = (
        '{"topic": "耳机产品推广", '
        '"minutes": "## 目标用户\\n- 面向年轻人", '
        '"decisions": "## 渠道决策\\n- 先做中腰部主播", '
        '"todos": "## 执行任务\\n- 【市场部】提交预算"}'
    )

    action_items, resolutions, minutes, normalized = normalize_structured_minutes_output(
        raw,
        "本次会议未明确待办事项。",
        "本次会议未明确决议。",
        title="测试会议",
        date="2026-06-21 23:01",
    )

    assert normalized is True
    assert "提交预算" in action_items
    assert "渠道决策" in resolutions
    assert minutes.startswith("# 会议纪要：测试会议")
    assert "## 一、会议主题" in minutes
    assert "## 二、目标用户" in minutes


def test_has_meaningful_minutes_content_rejects_degenerate_short_outputs():
    transcript = "这是一个很长的会议转录。" * 80

    assert _has_meaningful_minutes_content("基于", transcript) is False
    assert _has_meaningful_minutes_content("这段", transcript) is False
    assert _has_meaningful_minutes_content(
        "## 一、目标\n- 明确搬迁范围与时间\n- 安排现场勘察和停车统计\n## 二、执行计划\n- 周六统一搬运",
        transcript,
    ) is True


def test_minutes_chain_retries_when_minutes_body_is_too_short(monkeypatch):
    outputs = iter(
        [
            "基于",
            (
                '{"topic":"搬迁安排","minutes":"## 选址讨论\\n- 确认新办公区范围与楼层条件'
                '\\n- 评估会议室、工位和停车位需求\\n## 执行计划\\n- 周六统一搬运并提前装箱",'
                '"decisions":"## 决议\\n- 周六搬迁\\n- 先完成现场勘察",'
                '"todos":"## 待办\\n- 统计工位\\n- 汇总搬家预算"}'
            ),
        ]
    )

    monkeypatch.setattr(
        PromptTemplateLoader,
        "load",
        staticmethod(lambda scene, headings=None: RunnableLambda(lambda params: params)),
    )

    chain = MinutesChain(llm=RunnableLambda(lambda _: next(outputs)))
    action_items, resolutions, minutes = chain.run(
        "这是一个很长的会议转录。" * 120,
        title="测试会议",
        date="2026-06-21 23:50",
    )

    assert "统计工位" in action_items
    assert "周六搬迁" in resolutions
    assert minutes.startswith("# 会议纪要：测试会议")
    assert "选址讨论" in minutes
    assert "执行计划" in minutes
