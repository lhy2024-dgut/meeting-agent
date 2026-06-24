# -*- coding: utf-8 -*-
"""元宝纪要 HTML 可视化生成链

LLM 生成 <body> 内的 HTML 内容，Python 包装为完整 HTML 文件。
验证使用 BeautifulSoup；支持代码块/Mermaid 流程图开关。
"""

import re

from langchain_core.messages import HumanMessage, SystemMessage

from engines.llm import OllamaLLMError, get_llm
from logger import get_logger

logger = get_logger(__name__)

# ── CSS（元宝纪要风格）────────────────────────────────────────────────────────
_CSS = """\
*, *::before, *::after { box-sizing: border-box; }
body { background-color: #F7F8FA; color: #111; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; padding: 12px; font-size: 12px; }
.header { display: flex; flex-direction: column; gap: 4px; padding-bottom: 10px; border-bottom: 1px solid #EBEBEB; margin-bottom: 16px; }
.header-title { font-size: 20px; font-weight: bold; color: #006EFF; }
.header-meta { font-size: 12px; color: #888; }
.summary { font-size: 12px; background-color: #F2F7FF; border-left: 3px solid #006EFF; border-radius: 0 6px 6px 0; padding: 10px 12px; margin-bottom: 16px; line-height: 1.6; color: #333; }
.logic-chain { display: flex; flex-wrap: nowrap; align-items: stretch; justify-content: space-between; gap: 8px; margin-bottom: 16px; overflow-x: auto; }
.chain-node { flex: 1; min-width: 110px; background: #FFF; border: 1px solid #EBEBEB; border-radius: 6px; padding: 10px 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.02); }
.chain-node h4 { margin: 0 0 4px 0; font-size: 12px; color: #006EFF; }
.chain-node p { margin: 0; font-size: 11px; color: #555; line-height: 1.5; font-weight: bold; }
.chain-arrow { display: flex; align-items: center; justify-content: center; color: #C0C4CC; font-size: 16px; font-weight: bold; padding: 0 2px; flex-shrink: 0; }
.module-block { background-color: #FFF; border-radius: 10px; padding: 16px; margin-bottom: 16px; box-shadow: 0 2px 12px rgba(0,0,0,0.03); }
.module-title { font-size: 15px; font-weight: bold; margin: 0 0 12px 0; color: #111; }
.density-table { width: 100%; border-collapse: collapse; text-align: left; font-size: 12px; }
.density-table th { color: #111; font-weight: 700; padding: 8px 10px; border-bottom: 1px solid #F0F0F0; background-color: #F8F9FA; }
.density-table td { padding: 8px 10px; border-bottom: 1px solid #F0F0F0; color: #333; line-height: 1.5; }
.density-table tr:last-child td { border-bottom: none; }
.insight-stack { display: flex; flex-direction: column; gap: 8px; }
.insight-item { position: relative; padding: 10px 14px 10px 28px; border-radius: 6px; font-size: 12px; color: #222; line-height: 1.5; border: 1px solid transparent; }
.insight-item::before { content: '✦'; position: absolute; left: 10px; top: 10px; font-size: 12px; }
.insight-item:nth-child(4n+1) { background-color: #FFF9F0; border-color: #FFE4C4; }
.insight-item:nth-child(4n+1)::before { color: #FF9D00; }
.insight-item:nth-child(4n+2) { background-color: #F4FBF7; border-color: #C3E6CB; }
.insight-item:nth-child(4n+2)::before { color: #00A870; }
.insight-item:nth-child(4n+3) { background-color: #F8F6FF; border-color: #D8D0FF; }
.insight-item:nth-child(4n+3)::before { color: #7B61FF; }
.insight-item:nth-child(4n+4) { background-color: #F0F6FF; border-color: #C2D7FF; }
.insight-item:nth-child(4n+4)::before { color: #006EFF; }
.todo-title { color: #00B3A1; }
.risk-title { color: #E63946; }
pre.code-block { background: #1E1E1E; color: #D4D4D4; border-radius: 6px; padding: 12px; font-family: Consolas, Monaco, monospace; font-size: 11px; overflow-x: auto; margin: 8px 0; line-height: 1.5; }
.mermaid-container { background: #FAFAFA; border: 1px solid #EBEBEB; border-radius: 6px; padding: 12px; margin: 8px 0; text-align: center; }"""

_MERMAID_SCRIPT = (
    '<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>'
    "<script>mermaid.initialize({startOnLoad:true,theme:'neutral'});</script>"
)

# ── Prompts ───────────────────────────────────────────────────────────────────
_SYSTEM_BASE = """\
你是一位专业的会议纪要可视化助手，将会议信息转化为"一图看懂"的 HTML 可视化纪要，风格对标腾讯会议元宝纪要。

## 输出规则

1. 只输出 <body> 标签内的 HTML 内容（不含 <html>、<head>、<body> 标签本身，不含 CSS）。
2. 不使用 Markdown 代码块标记（不要用 ```html 包裹）。
3. 不在 HTML 前后输出任何解释文字。
4. 所有文本使用简体中文。

## HTML 结构要求（严格遵循以下顺序）

### 第一部分：头部信息
<div class="header">
  <div class="header-title">[会议标题]</div>
  <div class="header-meta">📅 [日期] &nbsp;|&nbsp; 👥 [从纪要/转录中提取参与人，无则写"参与人未记录"]</div>
</div>

### 第二部分：一句话摘要（50字以内，概括核心议题和主要结论）
<div class="summary">[摘要]</div>

### 第三部分：横向逻辑链（3-5个节点，展示会议主线推进逻辑）
<div class="logic-chain">
  <div class="chain-node"><h4>[emoji] [阶段名]</h4><p>[一句话要点]</p></div>
  <div class="chain-arrow">➔</div>
  <div class="chain-node"><h4>[emoji] [阶段名]</h4><p>[一句话要点]</p></div>
  <div class="chain-arrow">➔</div>
  <div class="chain-node"><h4>[emoji] [阶段名]</h4><p>[一句话要点]</p></div>
</div>

### 第四部分：议题模块（2-4个，每个重要议题一个模块）

洞察要点形式（适合讨论性内容）：
<div class="module-block">
  <div class="module-title">[emoji] [议题名称]</div>
  <div class="insight-stack">
    <div class="insight-item"><strong>[要点标题]</strong>：[具体内容，含结论/数据/依据]</div>
    <div class="insight-item"><strong>[要点标题]</strong>：[具体内容]</div>
  </div>
</div>

结构化表格形式（适合决策/对比内容）：
<div class="module-block">
  <div class="module-title">[emoji] [议题名称]</div>
  <table class="density-table">
    <thead><tr><th>事项</th><th>决策/现状</th><th>说明</th></tr></thead>
    <tbody><tr><td>[事项]</td><td>[内容]</td><td>[说明]</td></tr></tbody>
  </table>
</div>

### 第五部分：待办事项（必须包含，若无则写"本次会议无明确待办事项"）
<div class="module-block">
  <div class="module-title todo-title">📝 待办事项</div>
  <table class="density-table">
    <thead><tr><th>事项</th><th>责任人</th><th>截止时间</th></tr></thead>
    <tbody><tr><td>[任务描述]</td><td>[责任人]</td><td>[截止日期或"待定"]</td></tr></tbody>
  </table>
</div>

### 可选：风险点（若会议涉及风险，在待办之前插入）
<div class="module-block">
  <div class="module-title risk-title">⚠️ 风险点</div>
  <div class="insight-stack">
    <div class="insight-item"><strong>[风险名称]</strong>：[描述及应对]</div>
  </div>
</div>

## 内容要求

- insight-item 的彩色效果由 CSS nth-child 自动处理，无需手动加颜色。
- 要点须具体（含数据、方案、结论依据），禁止使用"讨论了某某"等笼统表述。
- 若决议内容存在，可在议题模块中体现，也可单独建"🎯 会议决议"模块。

## 【强制】禁止输出占位符

上方 HTML 结构示例中出现的所有 [xxx] 方括号标注，仅为格式说明，绝对不允许出现在最终输出中。
每一个 [xxx] 位置都必须替换为从会议信息中提取的真实内容：
- 参与人：从转录或纪要中提取，无法提取则写"参与人未记录"（不要保留方括号）
- 责任人：从待办/决议中提取，无明确信息则写"未记录"
- 截止时间：从待办中提取，无则写"待定"
- 其他所有 [xxx] 处：填入实际内容，若无相关信息则省略该行或写"未记录"
输出中出现任何 [ ] 方括号内含中文说明文字，均视为格式错误。"""

_CODE_ON = """\

## 代码块（已启用）
若会议涉及代码或技术方案，在相关模块内插入（若不涉及则不插入）：
<pre class="code-block"><code>[代码内容]</code></pre>"""

_CODE_OFF = "\n\n代码块显示已关闭，不要插入任何 <pre> 或 <code> 标签。"

_FLOWCHART_ON = """\

## Mermaid 流程图（已启用）
若会议涉及流程或架构设计，在相关模块内插入（若不涉及则不插入）：
<div class="mermaid-container">
  <div class="mermaid">
    graph TD
      A[步骤一] --> B[步骤二]
      B --> C[结果]
  </div>
</div>"""

_FLOWCHART_OFF = "\n\nMermaid 流程图显示已关闭，不要插入任何 mermaid 相关标签。"


def _build_system_prompt(show_code: bool, show_flowchart: bool) -> str:
    return _SYSTEM_BASE + (_CODE_ON if show_code else _CODE_OFF) + (
        _FLOWCHART_ON if show_flowchart else _FLOWCHART_OFF
    )


def _build_human_message(data: dict) -> str:
    title = data.get("title", "未命名会议")
    date = data.get("date", "")
    minutes = (data.get("minutes") or "")[:3000]
    action_items = (data.get("action_items") or "")[:800]
    resolutions = (data.get("resolutions") or "")[:500]
    transcript = (data.get("transcript") or "")[:500]

    return (
        f"请根据以下会议信息，生成可视化 HTML 纪要的 <body> 内容。\n\n"
        f"会议标题：{title}\n"
        f"会议时间：{date}\n\n"
        f"## 会议纪要\n{minutes}\n\n"
        f"## 待办事项\n{action_items}\n\n"
        f"## 会议决议\n{resolutions}\n\n"
        f"## 转录片段（供提取参与人）\n{transcript}\n\n"
        "请直接输出 HTML 标签，不要包含 <html>、<head>、<body> 标签，不要用 ```html 包裹。"
    )


# ── 占位符清理 ────────────────────────────────────────────────────────────────

# 匹配 [中文说明性占位符]，排除 Mermaid 节点语法（字母/数字紧跟的 [xxx]）
_PLACEHOLDER_RE = re.compile(r'(?<![A-Za-z0-9_])\[([^\]\n]{2,100})\]')


def _strip_placeholders(html: str) -> str:
    """将 LLM 未填写的 [xxx] 说明性占位符替换为合理默认值。

    Mermaid 流程图语法 A[节点名] 因前有字母标识符，不会被此正则命中。
    """
    def _replace(m: re.Match) -> str:
        inner = m.group(1)
        if any(kw in inner for kw in ("截止", "日期", "时间")):
            return "待定"
        if any(kw in inner for kw in ("参与人", "人员", "与会")):
            return "参与人未记录"
        if any(kw in inner for kw in ("责任人", "负责人")):
            return "未记录"
        # 长于 4 字符的 [中文说明] 均视为未填写的占位符
        if len(inner) > 4:
            return "未记录"
        return m.group(0)

    return _PLACEHOLDER_RE.sub(_replace, html)


# ── HTML 提取与验证 ───────────────────────────────────────────────────────────

def _extract_body_html(raw: str) -> str:
    """从 LLM 输出中提取 body 内容。

    兼容：模型输出整段 body 内容、带 <body> 标签、或带 markdown 代码块。
    """
    raw = raw.strip()
    # 移除 markdown 代码块标记
    raw = re.sub(r"```(?:html)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()

    # 若模型输出了完整 HTML，提取 <body> 内容
    body_match = re.search(r"<body[^>]*>([\s\S]*?)</body>", raw, re.IGNORECASE)
    if body_match:
        return _strip_placeholders(body_match.group(1).strip())

    # 若输出了完整 HTML 但无 <body> 标签，提取 <html> 之后的内容
    html_match = re.search(r"<html[^>]*>([\s\S]*?)$", raw, re.IGNORECASE)
    if html_match:
        inner = html_match.group(1)
        # 去掉 <head>...</head>
        inner = re.sub(r"<head[\s\S]*?</head>", "", inner, flags=re.IGNORECASE)
        return _strip_placeholders(inner.strip())

    # 否则直接返回（已经是 body 内容）
    return _strip_placeholders(raw)


def _wrap_html(body_content: str, title: str, show_flowchart: bool) -> str:
    """将 body 内容包装为完整合法 HTML 文件。"""
    mermaid_head = f"\n{_MERMAID_SCRIPT}" if show_flowchart else ""
    safe_title = title.replace("<", "&lt;").replace(">", "&gt;") if title else "会议纪要"
    return (
        f'<!DOCTYPE html>\n'
        f'<html lang="zh-CN">\n'
        f'<head>\n'
        f'<meta charset="UTF-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<title>{safe_title}</title>\n'
        f'<style>\n{_CSS}\n</style>'
        f'{mermaid_head}\n'
        f'</head>\n'
        f'<body>\n'
        f'{body_content}\n'
        f'</body>\n'
        f'</html>'
    )


def _validate_html(html: str) -> tuple[bool, str]:
    """用 BeautifulSoup 校验 HTML 合法性。"""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        if not soup.find("html"):
            return False, "缺少 <html> 标签"
        if not soup.find("body"):
            return False, "缺少 <body> 标签"
        return True, ""
    except ImportError:
        # BeautifulSoup 未安装时降级为基础检查
        if "<html" in html and "</html>" in html and "<body" in html and "</body>" in html:
            return True, ""
        return False, "HTML 结构不完整"
    except Exception as e:
        return False, str(e)


# ── 主链 ──────────────────────────────────────────────────────────────────────

class HtmlSummaryChain:
    """元宝纪要 HTML 可视化生成链。"""

    MAX_RETRY = 1

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.3, force_new=True)

    def run(
        self,
        data: dict,
        show_code: bool = False,
        show_flowchart: bool = False,
    ) -> tuple[str, str]:
        """生成可视化 HTML 纪要。

        Returns:
            (html, error_msg) — 成功时返回完整 HTML 字符串和空 error；
            失败时 html 为空，error_msg 描述原因。
        """
        system_prompt = _build_system_prompt(show_code, show_flowchart)
        human_msg = _build_human_message(data)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_msg),
        ]

        title = data.get("title", "会议纪要")
        last_error = ""

        for attempt in range(self.MAX_RETRY + 1):
            try:
                response = self.llm.invoke(messages)
                raw = response.content if hasattr(response, "content") else str(response)
            except OllamaLLMError as exc:
                last_error = f"LLM 调用失败：{exc}"
                if attempt < self.MAX_RETRY:
                    logger.warning("HTML 纪要生成失败，重试 %d/%d", attempt + 1, self.MAX_RETRY)
                    continue
                return "", last_error

            body_html = _extract_body_html(raw)
            if not body_html.strip():
                last_error = "LLM 未返回有效 HTML 内容"
                if attempt < self.MAX_RETRY:
                    logger.warning("未提取到 HTML 内容，重试 %d/%d", attempt + 1, self.MAX_RETRY)
                    continue
                return "", last_error

            full_html = _wrap_html(body_html, title, show_flowchart)
            valid, err = _validate_html(full_html)

            if valid:
                logger.info("HTML 纪要生成成功，共 %d 字符", len(full_html))
                return full_html, ""

            # 校验失败：最后一次尝试时仍返回结果（尽力而为）
            if attempt >= self.MAX_RETRY:
                logger.warning("HTML 校验未通过(%s)，仍返回结果", err)
                return full_html, ""

            logger.warning("HTML 校验失败(%s)，重试 %d/%d", err, attempt + 1, self.MAX_RETRY)

        return "", last_error
