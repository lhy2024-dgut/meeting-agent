"""
llm.py - 大模型调用模块（通过 Ollama 本地部署）
单次调用同时输出 summary / decisions / todos，速度快、语义一致。
"""

import os
import re
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

SYSTEM_PROMPT = """你是一位专业的会议纪要助手，擅长从会议录音转录中提炼关键信息，输出结构清晰、层次分明的会议纪要。

## 输出规则

1. 严格按下方 JSON 格式输出，不要输出任何其他内容，不要加 markdown 代码块标记。
2. JSON 只包含三个字段：summary、decisions、todos，不要添加其他字段。
3. 每个字段的值是使用 \\n 换行的字符串，不要使用真实换行符。
4. 禁止逐条复述原文，必须归纳提炼，用自己的语言概括。
5. 每个字段必须有二级标题（##），将内容相关的要点放在同一二级标题下，标题名称要有总结性。
6. 若某个二级标题下内容较多，可进一步用三级标题（###）细分同类内容。
7. 每条要点不超过 30 字，语言简洁，去除口语化表达。
8. 若某项内容在会议中未提及，对应字段输出"无"。

## 输出格式示例

{"summary": "## 开发进度\\n### 前端进展\\n- 论坛模块全部页面已完成，含发帖、评论、点赞功能\\n- 二手交易列表页完成，购买流程页预计差2天\\n### 后端进展\\n- 数据库迁移至微信云开发完成，查询效率提升30%\\n- 消息推送功能预计下周三完成\\n## 答辩安排\\n- 时间：下周五14:00，每组10分钟展示+5分钟问答\\n- 材料截止：下周三24:00", "decisions": "## 技术规范\\n- 代码提交须写清楚commit信息，禁止使用update、fix等模糊描述\\n## 产品规划\\n- 首页加载优化列入下版本核心目标\\n- 校园活动功能延期至下下版本", "todos": "## 开发任务\\n### 前端\\n- 【张三】完成购买流程页面开发（本周五）\\n- 【张三】修复商品搜索关键词高亮问题（明天）\\n### 后端\\n- 【李四】完成消息推送功能（下周三）\\n## 答辩准备\\n- 【前端同学】录制演示视频，覆盖论坛、交易、助手三模块，时长3分钟\\n- 【产品同学】制作答辩PPT\\n- 【全体】材料于下周三24:00前提交"}

注意：以上只是格式示例，实际输出请完全基于用户提供的会议转录内容。"""

_SEG_SUMMARY_SYSTEM = """你是会议助手。用一句话（20字以内）概括以下这段会议内容的核心。
直接输出概括内容，不要有任何前缀或多余符号。"""


def _chat(system_prompt: str, user_content: str) -> str:
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content}
            ],
            "stream": False
        },
        timeout=300
    )
    return resp.json()["message"]["content"].strip()


def _parse_llm_output(raw: str) -> dict:
    """三级容错解析：直接解析 → 正则提取JSON块 → 逐字段提取"""
    cleaned = raw.replace("```json", "").replace("```", "").strip()

    # 第一次：直接解析
    try:
        parsed = json.loads(cleaned)
        return {
            "summary":   parsed.get("summary",   "（未生成）"),
            "decisions": parsed.get("decisions", "（未生成）"),
            "todos":     parsed.get("todos",     "（未生成）"),
        }
    except json.JSONDecodeError:
        pass

    # 第二次：正则提取最外层 { } 块
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            return {
                "summary":   parsed.get("summary",   "（未生成）"),
                "decisions": parsed.get("decisions", "（未生成）"),
                "todos":     parsed.get("todos",     "（未生成）"),
            }
        except json.JSONDecodeError:
            pass

    # 第三次：逐字段正则提取
    print(f"[LLM] JSON解析失败，逐字段提取。原始片段：{raw[:200]}")

    def extract_field(text, key):
        pattern = rf'"{key}"\s*:\s*"(.*?)(?<!\\)"(?=\s*[,}}])'
        m = re.search(pattern, text, re.DOTALL)
        if m:
            return m.group(1).replace('\\"', '"').replace('\\n', '\n')
        return None

    return {
        "summary":   extract_field(cleaned, "summary")   or cleaned,
        "decisions": extract_field(cleaned, "decisions") or "（提取失败）",
        "todos":     extract_field(cleaned, "todos")     or "（提取失败）",
    }


def generate_all(transcript: str) -> dict:
    print("[LLM] 开始生成（单次调用）...")
    t = time.time()
    raw = _chat(SYSTEM_PROMPT, f"以下是本次会议的转录文本，请按要求生成会议纪要：\n\n{transcript}")
    llm_time = time.time() - t
    print(f"[LLM] 生成完成，耗时 {llm_time:.1f}s")

    result = _parse_llm_output(raw)
    result["transcript"] = transcript
    result["llm_time"]   = llm_time
    return result


def summarize_segment(segment_text: str) -> str:
    return _chat(_SEG_SUMMARY_SYSTEM, segment_text)