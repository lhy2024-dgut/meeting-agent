import uuid
import warnings

from langchain_core.chat_history import BaseChatMessageHistory, InMemoryChatMessageHistory
from langchain_core.output_parsers import StrOutputParser

# RunnableWithMessageHistory 在 langchain-core 1.x 中已弃用，推荐迁移到 LangGraph。
# 当前仍可用，先屏蔽弃用警告，待后续版本统一迁移。
warnings.filterwarnings("ignore", message=".*RunnableWithMessageHistory.*")
from langchain_core.runnables.history import RunnableWithMessageHistory

import config
from prompts.templates import CHAT_PROMPT


class ChatAgent:
    """会议问答 Agent，基于 LangChain RunnableWithMessageHistory + RAG"""

    _retriever = None

    def __init__(self):
        self.llm = config.get_llm(temperature=0.7)
        self._session_store = {}
        self.meeting_context = {}
        self._session_id = str(uuid.uuid4())[:8]

    @classmethod
    def _get_retriever(cls):
        if cls._retriever is None:
            from rag.retriever import get_retriever
            cls._retriever = get_retriever()
        return cls._retriever

    def set_meeting_context(self, transcript="", minutes="", action_items="", resolutions=""):
        self.meeting_context = {
            "transcript": (transcript or "")[:1000],
            "minutes": (minutes or "")[:500],
            "action_items": (action_items or "")[:300],
            "resolutions": (resolutions or "")[:300],
        }
        self._session_id = str(uuid.uuid4())[:8]

    def _get_session_history(self, session_id) -> BaseChatMessageHistory:
        if session_id not in self._session_store:
            self._session_store[session_id] = InMemoryChatMessageHistory()
        return self._session_store[session_id]

    def chat(self, user_message):
        # RAG 检索：从知识库搜索相关内容
        try:
            rag_context = self._get_retriever().build_context(user_message, top_k=5)
        except Exception as e:
            print(f"[WARN] RAG 检索失败: {e}")
            rag_context = ""
        if not rag_context:
            rag_context = "（暂无历史会议相关知识）"

        chain = CHAT_PROMPT | self.llm | StrOutputParser()
        chain_with_history = RunnableWithMessageHistory(
            chain,
            self._get_session_history,
            input_messages_key="question",
            history_messages_key="history",
        )
        response = chain_with_history.invoke(
            {**self.meeting_context, "rag_context": rag_context, "question": user_message},
            config={"configurable": {"session_id": self._session_id}},
        )
        return response or "抱歉，当前 LLM 未返回内容。"

    @staticmethod
    def get_suggested_questions():
        return [
            "会议的主要议题是什么？",
            "有哪些待办事项？",
            "会议决议有哪些？",
            "谁负责哪些任务？",
            "总结会议要点",
            "会议中提到的风险/问题",
        ]
