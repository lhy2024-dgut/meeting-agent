"""
chat_chain.py - 带 Memory 的对话链（LangChain 实现）

Memory 管理方式：
  不依赖 langchain.memory（新版已迁移，导入路径变化频繁），
  改用 chat_messages 列表手动管理对话历史，存储在 Streamlit 的
  session_state 里，每个用户会话独立，逻辑更清晰可控。

  chat_messages 格式：
  [
    {"role": "user",      "content": "你好"},
    {"role": "assistant", "content": "你好！有什么可以帮你？"},
    ...
  ]

  每次调用 chat() 时：
  1. 把 chat_messages 转成 LangChain 消息格式传给模型
  2. 把本轮 user/assistant 消息追加到 chat_messages
  3. 如果超过 20 条消息（10轮），自动裁剪最早的记录，防止上下文过长
"""

import os
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv

load_dotenv()

# ── 初始化模型
llm = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
    base_url="http://localhost:11434",
)

# ── Prompt 模板
# MessagesPlaceholder 会把历史对话列表插入到这个位置
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "你是会议助手。以下是本次会议的转录内容，请基于此回答用户的问题。"
     "如果问题与会议内容无关，也可以正常回答。\n\n"
     "【会议转录】\n{meeting_context}"),
    MessagesPlaceholder(variable_name="history"),  # 历史对话插入这里
    ("human", "{input}")
])

# ── 构建链
chain = prompt | llm | StrOutputParser()


def chat(user_input: str, meeting_context: str, chat_messages: list) -> str:
    """
    带记忆的单轮对话。

    参数：
        user_input      本轮用户输入
        meeting_context 会议转录文本（存在 session_state.last_transcript）
        chat_messages   对话历史列表（存在 session_state.chat_messages，由调用方维护）

    返回：
        模型回复字符串

    副作用：
        把本轮 user/assistant 消息追加到 chat_messages 列表
        如果历史超过 20 条消息自动裁剪最早的
    """

    # 把 chat_messages 转成 LangChain 消息对象列表
    history = []
    for msg in chat_messages:
        if msg["role"] == "user":
            history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            history.append(AIMessage(content=msg["content"]))

    # 调用链
    response = chain.invoke({
        "input":           user_input,
        "meeting_context": meeting_context[:2000] if meeting_context else "（本次未处理会议录音）",
        "history":         history
    })

    # 把本轮对话追加到历史（由调用方的 session_state 持久化）
    chat_messages.append({"role": "user",      "content": user_input})
    chat_messages.append({"role": "assistant", "content": response})

    # 超过 20 条（10轮）自动裁剪最早的 2 条，保持窗口大小
    if len(chat_messages) > 20:
        del chat_messages[:2]

    return response