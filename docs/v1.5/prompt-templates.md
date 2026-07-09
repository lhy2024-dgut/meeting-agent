# 场景化提示词模板系统

## 概览

v1.5 引入了场景化提示词模板系统，支持 5 种模板（1 个内置通用 + 4 个 YAML 场景）的前端切换。不同场景输出结构有明显差异。

## 目录结构

```
prompts/
└── templates/              # Python 包（替换原 templates.py）
    ├── __init__.py          # 导出 MINUTES_PROMPT、CHAT_PROMPT、PromptTemplateLoader
    ├── academic_meeting.yaml   # 学术组会
    ├── project_weekly.yaml     # 项目周会
    ├── customer_interview.yaml # 客户访谈
    └── project_kickoff.yaml    # 立项评审
```

## 输出格式变化

### 旧格式（v1.4）
LLM 输出三个 `===SECTION===` 分隔块，解析为 `action_items`、`resolutions`、`minutes`。

### 新格式（v1.5）
LLM 输出 JSON，含二级/三级标题，结构更清晰：

```json
{
  "topic": "会议核心概括（30字以内）",
  "minutes": "## 研究进展\n### 实验数据\n- 要点1\n- 要点2\n## 问题讨论\n- 要点",
  "decisions": "## 技术规范\n- 决议1\n## 进度要求\n- 决议2",
  "todos": "## 实验任务\n- 【张三】任务描述（截止日期）\n## 团队任务\n- 【全体】任务"
}
```

`MinutesChain.run()` 自动组装完整纪要文档（含标题、日期、会议主题），向下游透明。
旧 `===SECTION===` 格式保留作为回退，保持向后兼容。

## 场景模板对比

| 场景 | minutes 一级标题 | 侧重点 |
|------|-----------------|--------|
| 通用会议 | 根据内容自动归纳 | 通用，无特殊要求 |
| 学术组会 | 研究进展 / 问题讨论 / 学术交流 / 任务安排 | 实验数据、导师建议、文献分享 |
| 项目周会 | 开发进度 / 问题与风险 / 技术决策 / 下周计划 | 进度百分比、阻塞点、技术选型理由 |
| 客户访谈 | 客户背景 / 需求与痛点 / 现有方案评估 / 合作意向 | 痛点原话、预算决策链 |
| 立项评审 | 项目背景 / 技术方案 / 资源与排期 / 风险评估 / 评审结论 | 选型理由、评审结论、前置条件 |

## 新增场景（不改代码）

1. 在 `prompts/templates/` 目录下新建 `my_scene.yaml`
2. 参照下方模板结构填写字段
3. 重启应用后前端自动出现新选项

```yaml
# 场景名称（唯一键）
scene: 我的场景
display_name: 我的场景
description: 场景描述（展示在前端）

# 场景特定说明：引导 LLM 关注重点（附加到通用规则后）
scene_context: |
  本次会议类型：xxx。请重点关注：
  - 关注点1
  - 关注点2

# minutes 字段的一级分类标题
minutes_headings:
  - 标题一
  - 标题二
  - 标题三

# few-shot 示例（output 用单引号，\n 保持字面量）
example:
  description: 示例场景描述
  output: '{"topic": "...", "minutes": "## 标题一\n- 要点", "decisions": "## 类别\n- 内容", "todos": "## 分类\n- 【人】任务（日期）"}'

# 负面约束
negative_constraints:
  - 不要...
  - 不要...
```

## 使用方式

### 前端
上传页新增"会议场景模板"下拉框，选择场景后显示默认结构预览。
高级选项中可逐条添加自定义一级标题，覆盖场景默认结构。

### 代码调用
```python
from prompts.templates import PromptTemplateLoader

# 加载场景模板
pt = PromptTemplateLoader.load("学术组会")

# 加载场景 + 自定义标题
pt = PromptTemplateLoader.load("学术组会", custom_headings=["专项进展", "开放讨论"])

# 列出所有场景
scenes = PromptTemplateLoader.list_scenes()

# 获取场景预览（用于 UI）
preview = PromptTemplateLoader.get_preview("项目周会")
# -> {"description": "...", "headings": ["开发进度", ...], "example_input": "..."}
```

### MinutesChain
`MinutesChain.run()` 接受 `scene` 和 `custom_headings` 参数：
```python
action_items, resolutions, minutes = chain.run(
    transcript,
    title="项目周会 2026-05-25",
    date="2026-05-25",
    scene="项目周会",
    custom_headings=["自定义标题"],  # 可选，覆盖场景默认
)
```

## ASR 简体中文优化

`engines/asr_engine.py` 在 Faster-Whisper 调用中加入：
```python
initial_prompt="以下是普通话会议录音，请使用简体中文输出。"
```
解决转写结果出现繁体字的问题。
