"""会议纪要提示词模板模块

导出：
- MINUTES_PROMPT  : 默认（通用会议）纪要提取模板（向后兼容）
- CHAT_PROMPT     : 会议问答模板（不变）
- PromptTemplateLoader : 场景化模板加载器，从 *.yaml 动态加载
"""

from pathlib import Path
from typing import Optional

import yaml
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


_TEMPLATES_DIR = Path(__file__).parent


def _escape_braces(text: str) -> str:
    """转义 LangChain 模板中的 { } 为 {{ }}，防止被识别为模板变量。"""
    return text.replace("{", "{{").replace("}", "}}")


# ─── 基础 Prompt 组件（所有场景共用）────────────────────────────────────────

_BASE_RULES = r"""## 输出规则

1. 严格按下方 JSON 格式输出，不要输出任何其他内容，不要加 markdown 代码块标记。
2. 每个字段的值使用 \n 换行的字符串，不要使用真实换行符。
3. 禁止逐条复述原文，须归纳提炼核心信息，用自己的语言概括。
4. 【强制】minutes、decisions、todos 三个字段，必须先用 ## 二级标题对内容分组，再在标题下列要点。严禁直接输出无标题的散装要点列表（即不允许在没有任何 ## 的情况下就直接写 - 要点）。
5. 【强制】同一 ## 标题下若包含多个子类别，必须进一步用 ### 三级标题细分，将同类内容归在一起。
6. 每条要点须包含具体信息（涉及数据、方案选型、结论依据、负责人、截止日期等），禁止使用"讨论了某某问题""涉及了某某方面"等笼统表述，要写清楚讨论的内容和结果。
7. 若某项内容在会议中未提及，对应字段输出"无"。
8. topic 字段：用自己的语言（80 字以内）归纳本次会议讨论的核心内容，【严禁】直接复制或仅改写会议标题，必须基于转录内容提炼，不加任何前缀或符号。
9. short_summary 字段：用简洁的中文概括核心议题、关键讨论点和主要结论（≤200 字），纯文本一段话，不分标题、不逐条复述原文。
10. project_name 字段：从会议主题和内容推断项目名称（≤20 字），简洁明确（如"Q3 预算评审"）；无法确定具体项目时填"未分类"。"""

# 注意：{{ 和 }} 是 LangChain 模板中对 { } 的转义写法，LLM 最终收到的是单括号
_BASE_FORMAT = r"""## 输出格式示例（必须遵守标题层级，禁止散装要点）

{{"topic": "基于转录内容归纳的核心议题概括（80字以内，禁止照搬标题）", "minutes": "## 讨论议题A\n### 子类别（同议题内容较多时使用）\n- 具体结论或数据，说明原因或背景\n- 另一具体要点，包含关键细节\n## 讨论议题B\n- 具体要点，包含方案或决定的依据", "decisions": "## 决策类别\n- 明确决议内容及选择理由", "todos": "## 任务分类\n- 【负责人】具体任务描述（截止日期）", "short_summary": "用一段话概括本次会议的核心议题、关键讨论点与主要结论（200字以内）", "project_name": "从内容推断的项目名（20字以内，无法确定填未分类）"}}"""


def _build_scene_format(headings: list) -> str:
    """为特定场景生成含实际标题名的格式示例，引导小模型输出正确标题。

    返回值会被放入 LangChain ChatPromptTemplate 的 system 字段，
    {{ }} 是 LangChain 对字面量花括号的转义写法（LLM 最终收到单括号）。
    字符串内的 \\n 是两字符序列（反斜杠 + n），对应 JSON 字符串值里的换行转义。
    """
    h0 = _escape_braces(headings[0]) if len(headings) > 0 else "主要议题"
    h1 = _escape_braces(headings[1]) if len(headings) > 1 else "次要议题"
    # 逐段拼接，避免 f-string 与 {{ }} 混用导致混乱
    minutes_example = (
        '"minutes": "## ' + h0 + '\\n'
        + '### 子类别（同类内容较多时使用）\\n'
        + '- 具体要点，包含关键细节\\n'
        + '## ' + h1 + '\\n'
        + '- 具体要点，说明结论或依据"'
    )
    return (
        "## 输出格式示例（minutes 中的 ## 标题须与上方列表完全一致，禁止散装要点）\n\n"
        + '{{"topic": "基于转录内容归纳的核心议题概括（80字以内，禁止照搬标题）", '
        + minutes_example
        + ', "decisions": "## 决策类别\\n- 明确决议内容及选择理由"'
        + ', "todos": "## 任务分类\\n- 【负责人】具体任务描述（截止日期）"'
        + ', "short_summary": "用一段话概括核心议题、关键讨论点与主要结论（200字以内）"'
        + ', "project_name": "从内容推断的项目名（20字以内，无法确定填未分类）"}}'
    )

# 用字符串拼接而非 f-string，保留 _BASE_FORMAT 中的 {{ }} 不被 f-string 展开
_DEFAULT_SYSTEM = "\n\n".join([
    "你是一位专业的会议纪要助手，擅长从会议录音转录中提炼关键信息，输出结构清晰、层次分明的会议纪要。",
    _BASE_RULES,
    "minutes 字段：根据会议内容自动归纳 2-4 个 ## 二级标题（如「议题讨论」「技术方案」「进度同步」等），每个标题下列出具体要点；内容较多时必须用 ### 三级标题进一步细分。要点须写清楚讨论内容和结论，不能只写议题名称。",
    _BASE_FORMAT,
])


# ─── 默认模板（向后兼容）─────────────────────────────────────────────────────

MINUTES_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _DEFAULT_SYSTEM),
    ("human", "会议标题：{title}\n日期：{date}\n\n会议转录文本：\n{transcript}"),
])

CHAT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你正在讨论一场会议，以下为会议相关信息：

会议转录摘要：{transcript}
会议纪要：{minutes}
待办事项：{action_items}
会议决议：{resolutions}

## 知识库检索结果（来自历史会议）
{rag_context}

请基于以上所有信息回答用户问题。优先使用当前会议信息；若问题涉及历史会议内容或需要跨会议对比，则使用知识库检索结果。要求：准确、简洁、不编造内容。"""),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{question}"),
])


# ─── PromptTemplateLoader ────────────────────────────────────────────────────

class PromptTemplateLoader:
    """场景化提示词模板加载器。

    从 prompts/templates/*.yaml 动态加载场景模板，支持运行时切换。
    "通用会议"（默认）使用内置模板，无需 YAML 文件。

    新增场景只需在 prompts/templates/ 目录下添加 *.yaml 文件，无需修改代码。
    """

    DEFAULT_SCENE = "通用会议"

    @classmethod
    def list_scenes(cls) -> list[dict]:
        """返回所有可用场景信息列表（含通用会议）。

        每个元素包含：scene、display_name、description。
        """
        scenes = [
            {
                "scene": cls.DEFAULT_SCENE,
                "display_name": cls.DEFAULT_SCENE,
                "description": "适用于各类型会议的通用模板，根据内容自动归纳分类",
            }
        ]
        for yaml_path in sorted(_TEMPLATES_DIR.glob("*.yaml")):
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if not data or "scene" not in data:
                    continue
                scenes.append({
                    "scene": data["scene"],
                    "display_name": data.get("display_name", data["scene"]),
                    "description": data.get("description", ""),
                })
            except Exception:
                pass
        return scenes

    @classmethod
    def get_preview(cls, scene: str) -> dict:
        """返回场景预览信息，用于 UI 展示。

        返回：{"description": str, "headings": list[str], "example_input": str}
        """
        if scene == cls.DEFAULT_SCENE:
            return {
                "description": "适用于各类型会议的通用模板，根据内容自动归纳分类",
                "headings": [],
                "example_input": "",
            }
        yaml_path = cls._find_yaml(scene)
        if not yaml_path:
            return {"description": "", "headings": [], "example_input": ""}
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        return {
            "description": data.get("description", ""),
            "headings": data.get("minutes_headings", []),
            "example_input": data.get("example", {}).get("description", ""),
        }

    @classmethod
    def load(cls, scene: str, custom_headings: Optional[list] = None) -> ChatPromptTemplate:
        """加载指定场景的提示词模板。

        Args:
            scene: 场景名称（如 "学术组会"），不存在时回退到默认模板。
            custom_headings: 用户自定义一级标题列表，非空时覆盖场景默认标题。

        Returns:
            ChatPromptTemplate，human message 包含 {title}、{date}、{transcript} 占位符。
        """
        if scene == cls.DEFAULT_SCENE and not custom_headings:
            return MINUTES_PROMPT

        if scene == cls.DEFAULT_SCENE:
            return cls._build_prompt(
                scene_context="",
                headings=custom_headings or [],
                negative_constraints=[],
                example={},
            )

        yaml_path = cls._find_yaml(scene)
        if not yaml_path:
            return MINUTES_PROMPT

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        headings = custom_headings if custom_headings else data.get("minutes_headings", [])

        return cls._build_prompt(
            scene_context=data.get("scene_context", ""),
            headings=headings,
            negative_constraints=data.get("negative_constraints", []),
            example=data.get("example", {}),
        )

    # ── 内部方法 ────────────────────────────────────────────────────────────

    @classmethod
    def _find_yaml(cls, scene: str) -> Optional[Path]:
        """按 scene 字段值查找对应的 YAML 文件。"""
        for yaml_path in _TEMPLATES_DIR.glob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if data and data.get("scene") == scene:
                    return yaml_path
            except Exception:
                pass
        return None

    @classmethod
    def _build_prompt(
        cls,
        scene_context: str,
        headings: list,
        negative_constraints: list,
        example: dict,
    ) -> ChatPromptTemplate:
        """根据场景参数构建 ChatPromptTemplate。

        所有来自外部（YAML/用户输入）的字符串须经 _escape_braces() 处理，
        防止 { } 被 LangChain 误判为模板变量。
        """
        parts = [
            "你是一位专业的会议纪要助手，擅长从会议录音转录中提炼关键信息，输出结构清晰、层次分明的会议纪要。"
        ]

        if scene_context:
            parts.append(_escape_braces(scene_context.strip()))

        parts.append(_BASE_RULES)

        if headings:
            heading_list = "\n".join(
                f"  {i + 1}. {_escape_braces(h)}" for i, h in enumerate(headings)
            )
            parts.append(
                "【强制】minutes 字段的 ## 标题必须严格按照以下列表的顺序和名称输出，"
                "不允许新增、合并、改写或省略任何标题。"
                "若某标题下本次会议无相关内容，在该标题下写【无相关内容】：\n"
                + heading_list
            )
            parts.append(_build_scene_format(headings))
        else:
            parts.append(
                "minutes 字段：根据会议内容自动归纳 2-4 个 ## 二级标题，"
                "每个标题下列出具体要点；内容较多时必须用 ### 三级标题进一步细分。"
                "要点须写清楚讨论内容和结论，不能只写议题名称。"
            )
            parts.append(_BASE_FORMAT)

        if example and example.get("output"):
            desc = _escape_braces(example.get("description", ""))
            output = _escape_braces(example.get("output", ""))
            example_block = f"## 输出示例"
            if desc:
                example_block += f"\n场景：{desc}"
            example_block += f"\n\n输出：{output}"
            parts.append(example_block)

        if negative_constraints:
            constraints_text = "\n".join(
                f"- {_escape_braces(str(c))}" for c in negative_constraints
            )
            parts.append(f"## 负面约束（以下情况不应出现）\n{constraints_text}")

        system_prompt = "\n\n".join(parts)

        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "会议标题：{title}\n日期：{date}\n\n会议转录文本：\n{transcript}"),
        ])
