"""HTML summary generation for meeting minutes."""

import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

import config
from engines.llm import OllamaLLMError, get_llm
from logger import get_logger

logger = get_logger(__name__)

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
.insight-item::before { content: '*'; position: absolute; left: 10px; top: 10px; font-size: 12px; }
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
.mermaid-container { background: #FAFAFA; border: 1px solid #EBEBEB; border-radius: 6px; padding: 12px; margin: 8px 0; text-align: center; }
"""

_MERMAID_SCRIPT = (
    '<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>'
    "<script>mermaid.initialize({startOnLoad:true,theme:'neutral'});</script>"
)

_PLACEHOLDER_RE = re.compile(r"(?<![A-Za-z0-9_])\[([^\]\n]{2,100})\]")

_SYSTEM_BASE = """\
你是一位专业的会议纪要可视化助手，将会议信息转化为“一图看懂”的 HTML 可视化纪要，风格对标腾讯会议元宝纪要。

## 输出规则

1. 只输出 <body> 标签内的 HTML 内容，不包含 <html>、<head>、<body> 标签本身。
2. 不使用 Markdown 代码块包裹输出。
3. 不在 HTML 前后输出任何解释文字。
4. 所有文本使用简体中文。

## HTML 结构要求

1. 头部信息：会议标题、日期、参与人
2. 一句话摘要：50 字以内
3. 横向逻辑链：3-5 个节点
4. 议题模块：2-4 个
5. 待办事项：必须包含，若无则写“本次会议无明确待办事项”
6. 若存在风险，在待办事项前增加风险模块

请优先使用以下类名：
- header/header-title/header-meta
- summary
- logic-chain/chain-node/chain-arrow
- module-block/module-title
- density-table
- insight-stack/insight-item
- todo-title/risk-title

禁止把 [会议标题] 这类说明性占位符原样输出到结果里。
"""

_CODE_ON = """

如果会议涉及代码或技术方案，可在相关模块内插入：
<pre class="code-block"><code>代码内容</code></pre>
"""

_CODE_OFF = "\n\n代码块显示已关闭，不要插入任何 <pre> 或 <code> 标签。"

_FLOWCHART_ON = """

如果会议涉及流程或架构设计，可在相关模块内插入：
<div class="mermaid-container">
  <div class="mermaid">
    graph TD
      A[步骤一] --> B[步骤二]
      B --> C[结果]
  </div>
</div>
"""

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


def _strip_placeholders(html: str) -> str:
    def replace(match: re.Match) -> str:
        inner = match.group(1)
        if any(key in inner for key in ("截止", "日期", "时间")):
            return "待定"
        if any(key in inner for key in ("参与人", "人员", "与会")):
            return "参与人未记录"
        if any(key in inner for key in ("责任人", "负责人")):
            return "未记录"
        if len(inner) > 4:
            return "未记录"
        return match.group(0)

    return _PLACEHOLDER_RE.sub(replace, html)


def _extract_body_html(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"```(?:html)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()

    body_match = re.search(r"<body[^>]*>([\s\S]*?)</body>", raw, re.IGNORECASE)
    if body_match:
        return _strip_placeholders(body_match.group(1).strip())

    html_match = re.search(r"<html[^>]*>([\s\S]*?)$", raw, re.IGNORECASE)
    if html_match:
        inner = re.sub(r"<head[\s\S]*?</head>", "", html_match.group(1), flags=re.IGNORECASE)
        return _strip_placeholders(inner.strip())

    return _strip_placeholders(raw)


def _wrap_html(body_content: str, title: str, show_flowchart: bool) -> str:
    mermaid_head = f"\n{_MERMAID_SCRIPT}" if show_flowchart else ""
    safe_title = title.replace("<", "&lt;").replace(">", "&gt;") if title else "会议纪要"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f"<title>{safe_title}</title>\n"
        f"<style>\n{_CSS}\n</style>{mermaid_head}\n"
        "</head>\n"
        "<body>\n"
        f"{body_content}\n"
        "</body>\n"
        "</html>\n"
    )


def _validate_html(html: str) -> tuple[bool, str]:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        if not soup.find("html"):
            return False, "missing html tag"
        if not soup.find("body"):
            return False, "missing body tag"
        return True, ""
    except ImportError:
        if "<html" in html and "</html>" in html and "<body" in html and "</body>" in html:
            return True, ""
        return False, "HTML structure incomplete"
    except Exception as exc:
        return False, str(exc)


def get_html_summary_path(meeting_id: int) -> Path:
    return config.OUTPUT_DIR / f"meeting_{meeting_id}_summary.html"


class HtmlSummaryChain:
    MAX_RETRY = 1

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.3, force_new=True)

    def run(
        self,
        data: dict,
        show_code: bool = False,
        show_flowchart: bool = True,
    ) -> tuple[str, str]:
        messages = [
            SystemMessage(content=_build_system_prompt(show_code, show_flowchart)),
            HumanMessage(content=_build_human_message(data)),
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

            if attempt >= self.MAX_RETRY:
                logger.warning("HTML 校验未通过(%s)，仍返回结果", err)
                return full_html, ""

            logger.warning("HTML 校验失败(%s)，重试 %d/%d", err, attempt + 1, self.MAX_RETRY)

        return "", last_error

    def save(self, meeting_id: int, html: str) -> str:
        path = get_html_summary_path(meeting_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return str(path)
