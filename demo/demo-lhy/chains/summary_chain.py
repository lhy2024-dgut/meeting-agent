"""
summary_chain.py - 用 LangChain 构建的纪要生成链
对比原来的 llm.py：
  - 不用手写 requests.post
  - 不用手写 json.loads
  - Prompt 用模板管理，更清晰
  - 输出解析自动处理
"""

import time
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from dotenv import load_dotenv
import os

load_dotenv()

# ── 初始化模型
# 封装了 Ollama 的 API 调用，不用手写 requests
llm = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
    base_url="http://localhost:11434",
    temperature=0.3   # 降低随机性，纪要类任务要稳定输出
)

# ── Prompt 模板
SYSTEM = """你是专业会议纪要助手。严格按 JSON 格式输出，只包含三个字段：summary、decisions、todos。
不要加 markdown 代码块标记，不要添加其他字段。
每个字段用 \\n 换行，必须有二级标题（##），内容多时用三级标题（###）细分。
禁止逐条复述原文，归纳提炼，每条不超过30字。

示例格式：
{{"summary": "## 开发进度\\n### 前端\\n- 论坛模块完成\\n## 答辩安排\\n- 下周五14:00", "decisions": "## 技术规范\\n- commit须写清楚改动", "todos": "## 开发任务\\n### 前端\\n- 【张三】完成购买流程页（本周五）"}}"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM),
    ("human", "以下是会议转录文本，请生成纪要：\n\n{transcript}")
])

# ── 构建链：prompt | llm | parser
# 自动把模型输出解析成 Python 字典，不用手写 json.loads
parser = JsonOutputParser()
summary_chain = prompt | llm | parser


def generate_all(transcript: str) -> dict:
    """调用链生成纪要，接口和原 llm.py 保持一致，main.py 不需要改"""
    print("[LangChain] 开始生成纪要...")
    t = time.time()

    try:
        result = summary_chain.invoke({"transcript": transcript})
    except Exception as e:
        # JsonOutputParser 解析失败时降级处理
        print(f"[LangChain] 解析失败，降级处理：{e}")
        raw = (prompt | llm).invoke({"transcript": transcript}).content
        import re, json
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(match.group()) if match else {
            "summary": raw, "decisions": "（解析失败）", "todos": "（解析失败）"
        }

    llm_time = time.time() - t
    print(f"[LangChain] 生成完成，耗时 {llm_time:.1f}s")

    return {
        "summary":   result.get("summary",   "（未生成）"),
        "decisions": result.get("decisions", "（未生成）"),
        "todos":     result.get("todos",     "（未生成）"),
        "transcript": transcript,
        "llm_time":   llm_time,
    }