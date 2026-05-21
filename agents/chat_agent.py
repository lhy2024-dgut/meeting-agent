import uuid
import warnings

from langchain_core.chat_history import BaseChatMessageHistory, InMemoryChatMessageHistory
from langchain_core.output_parsers import StrOutputParser

warnings.filterwarnings("ignore", message=".*RunnableWithMessageHistory.*")
from langchain_core.runnables.history import RunnableWithMessageHistory

from engines.llm import get_llm
from logger import get_logger
from prompts.templates import CHAT_PROMPT
from rag.retriever import get_retriever

logger = get_logger(__name__)


class ChatAgent:
    """会议问答 Agent，支持依赖注入"""

    MAX_TRANSCRIPT_LEN = 6000
    MAX_MINUTES_LEN = 2000
    MAX_ITEMS_LEN = 1000

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.7)
        self._session_store = {}
        self.meeting_context = {}
        self._session_id = str(uuid.uuid4())[:8]

    def set_meeting_context(self, transcript="", minutes="", action_items="", resolutions="", meeting_id=None):
        transcript = transcript or ""
        minutes = minutes or ""
        action_items = action_items or ""
        resolutions = resolutions or ""

        for name, val, limit in [
            ("transcript", transcript, self.MAX_TRANSCRIPT_LEN),
            ("minutes", minutes, self.MAX_MINUTES_LEN),
            ("action_items", action_items, self.MAX_ITEMS_LEN),
            ("resolutions", resolutions, self.MAX_ITEMS_LEN),
        ]:
            if len(val) > limit:
                logger.warning(
                    "ChatAgent 上下文截断: %s (%d -> %d 字符)", name, len(val), limit,
                )

        self.meeting_context = {
            "transcript": transcript[:self.MAX_TRANSCRIPT_LEN],
            "minutes": minutes[:self.MAX_MINUTES_LEN],
            "action_items": action_items[:self.MAX_ITEMS_LEN],
            "resolutions": resolutions[:self.MAX_ITEMS_LEN],
            "meeting_id": meeting_id,
        }
        self._session_id = str(uuid.uuid4())[:8]

    def _get_session_history(self, session_id) -> BaseChatMessageHistory:
        if session_id not in self._session_store:
            if len(self._session_store) >= 16:
                self._session_store.pop(next(iter(self._session_store)))
            self._session_store[session_id] = InMemoryChatMessageHistory()
        history = self._session_store[session_id]
        if len(history.messages) > 20:
            history.messages = history.messages[-20:]
        return history

    def chat(self, user_message):
        try:
            rag_context = get_retriever().build_context(
                user_message, top_k=5,
                exclude_meeting_id=self.meeting_context.get("meeting_id"),
            )
        except Exception as e:
            logger.warning("RAG 检索失败: %s", e)
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
