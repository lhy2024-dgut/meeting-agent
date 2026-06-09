"""
ChatAgent — 基于 LangGraph MemorySaver 的多轮对话，10 轮滑窗，会议隔离。

架构演进: RunnableWithMessageHistory (deprecated) → LangGraph StateGraph + MemorySaver
- 每个会议独立 checkpoint thread，切换会议不串台
- 10 轮滑动窗口，超出自动裁剪最早对话
- 前端可读取轮次计数与裁剪状态
"""

import operator
import uuid
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from engines.llm import get_llm
from logger import get_logger
from rag.retriever import get_retriever

logger = get_logger(__name__)


class ChatState(TypedDict):
    """自定义 State，用 operator.add 简单拼接消息，避免 add_messages 合并行为"""
    messages: Annotated[list, operator.add]


class ChatAgent:
    """会议问答 Agent，支持依赖注入"""

    MAX_ROUNDS = 10
    MAX_TRANSCRIPT_LEN = 6000
    MAX_MINUTES_LEN = 2000
    MAX_ITEMS_LEN = 1000
    MAX_USER_INPUT_LEN = 500

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.7)
        self._checkpointer = MemorySaver()
        self.meeting_context = {}
        self._thread_id = str(uuid.uuid4())[:8]
        self._latest_rag_context = ""
        self._latest_rag_results = []
        self._trimmed = False
        self._round_count = 0
        self._cross_meeting = False

        # Build graph: single node that builds context + calls LLM
        builder = StateGraph(ChatState)
        builder.add_node("chat", self._chat_node)
        builder.add_edge(START, "chat")
        builder.add_edge("chat", END)
        self._graph = builder

    # ── Public API ──

    def set_meeting_context(
        self, transcript="", minutes="", action_items="", resolutions="",
        meeting_id=None, cross_meeting=False,
    ):
        """注入会议上下文；切换会议时自动生成新 thread_id，Memory 完全隔离。
        cross_meeting=True 时不注入具体会议内容，RAG 搜索所有会议。
        """
        self._cross_meeting = cross_meeting
        if cross_meeting:
            self.meeting_context = {
                "transcript": "", "minutes": "", "action_items": "",
                "resolutions": "", "meeting_id": None,
            }
            self._thread_id = f"cross_{uuid.uuid4().hex[:8]}"
            self._trimmed = False
            self._round_count = 0
            self._latest_rag_context = ""
            self._latest_rag_results = []
            return

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
                logger.warning("ChatAgent 上下文截断: %s (%d -> %d)", name, len(val), limit)

        self.meeting_context = {
            "transcript": transcript[: self.MAX_TRANSCRIPT_LEN],
            "minutes": minutes[: self.MAX_MINUTES_LEN],
            "action_items": action_items[: self.MAX_ITEMS_LEN],
            "resolutions": resolutions[: self.MAX_ITEMS_LEN],
            "meeting_id": meeting_id,
        }
        # 新会议 → 新 thread，checkpoint 完全隔离，不可能串台
        self._thread_id = f"meeting_{meeting_id}_{uuid.uuid4().hex[:8]}"
        self._trimmed = False
        self._round_count = 0
        self._latest_rag_context = ""
        self._latest_rag_results = []

    def chat(self, user_message: str) -> str:
        """一问一答；每次自动走 MemorySaver 记录对话历史"""
        try:
            retriever = get_retriever()
            if self._cross_meeting:
                results = retriever.search(user_message, top_k=5)
            else:
                results = retriever.search(
                    user_message,
                    top_k=5,
                    meeting_id=self.meeting_context.get("meeting_id"),
                )
            self._latest_rag_results = retriever.enrich_results(results)
            rag_context = retriever.build_context(results=results)
        except Exception as e:
            logger.warning("RAG 检索失败: %s", e)
            rag_context = ""
            self._latest_rag_results = []
        self._latest_rag_context = rag_context or "（暂无相关知识库内容）"

        app = self._graph.compile(checkpointer=self._checkpointer)
        result = app.invoke(
            {"messages": [HumanMessage(content=user_message)]},
            config={"configurable": {"thread_id": self._thread_id}},
        )
        response = result["messages"][-1].content or "抱歉，当前 LLM 未返回内容。"
        self._round_count += 1
        return response

    def get_memory_stats(self) -> dict:
        """供前端读取轮次/裁剪状态"""
        return {
            "round_count": self._round_count,
            "max_rounds": self.MAX_ROUNDS,
            "is_full": self._round_count >= self.MAX_ROUNDS,
            "trimmed": self._trimmed,
        }

    def get_latest_rag_results(self) -> list:
        """供前端展示历史会议引用来源。
        每条含 meeting_title / chunk_type_label / text / score。
        """
        return self._latest_rag_results

    @staticmethod
    def validate_input(user_input: str) -> str | None:
        """前端校验，返回错误信息或 None"""
        if not user_input or not user_input.strip():
            return "请输入问题内容"
        if len(user_input) > ChatAgent.MAX_USER_INPUT_LEN:
            return f"问题过长，请控制在 {ChatAgent.MAX_USER_INPUT_LEN} 字以内"
        return None

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

    # ── Graph Node ──

    def _chat_node(self, state: ChatState, config):
        """LangGraph node: 拼接 system prompt → 滑窗裁剪 → 调用 LLM"""
        all_msgs = list(state.get("messages", []))

        # Build fresh system prompt (includes latest RAG context)
        ctx = self.meeting_context
        if self._cross_meeting:
            system_text = (
                "你是一个会议助手，负责从历史会议知识库中检索并回答问题。\n\n"
                "## 知识库召回结果\n"
                f"{self._latest_rag_context}\n\n"
                "回答规则：\n"
                "1. 根据知识库召回内容回答，明确说明信息来源于哪场会议。\n"
                "2. 跨会议对比时，分别引用各会议内容。\n"
                "3. 若知识库中没有相关信息，请明确告知，不要编造。\n"
                "4. 回答应准确、简洁。"
            )
        else:
            system_text = (
                f"你正在讨论一场会议，以下为会议相关信息：\n\n"
                f"会议转录摘要：{ctx.get('transcript', '')}\n"
                f"会议纪要：{ctx.get('minutes', '')}\n"
                f"待办事项：{ctx.get('action_items', '')}\n"
                f"会议决议：{ctx.get('resolutions', '')}\n\n"
                f"## 知识库召回 Top-5\n"
                f"{self._latest_rag_context}\n\n"
                f"回答规则（按优先级）：\n"
                f"1. 优先依据当前会议内容回答用户问题。\n"
                f"2. 若当前会议内容不足，可参考知识库召回的相关片段，引用时注明来源会议。\n"
                f"3. 若知识库中没有足够依据，请明确告知，不要编造。\n"
                f"4. 回答应准确、简洁。"
            )

        # Separate system from conversation messages
        non_system = [m for m in all_msgs if not isinstance(m, SystemMessage)]

        # 10-round sliding window: keep max 20 non-system messages
        max_msgs = self.MAX_ROUNDS * 2
        if len(non_system) > max_msgs:
            non_system = non_system[-max_msgs:]
            self._trimmed = True
            logger.info("Memory 滑窗裁剪: 保留最近 %d 条消息", max_msgs)

        llm_messages = [SystemMessage(content=system_text)] + non_system
        response = self.llm.invoke(llm_messages)
        return {"messages": [response]}
