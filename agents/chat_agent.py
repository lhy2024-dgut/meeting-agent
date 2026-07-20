"""Chat agent with meeting-scoped memory, RAG grounding, and timeout fallback."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import operator
import uuid
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from engines.llm import get_llm
from logger import get_logger
from rag.retriever import get_retriever

logger = get_logger(__name__)


class ChatState(TypedDict):
    messages: Annotated[list, operator.add]


class ChatAgent:
    MAX_ROUNDS = 10
    MAX_TRANSCRIPT_LEN = 6000
    MAX_MINUTES_LEN = 2000
    MAX_ITEMS_LEN = 1000
    MAX_USER_INPUT_LEN = 500
    LLM_TIMEOUT_SECONDS = 20

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.7)
        self._checkpointer = MemorySaver()
        self.meeting_context: dict[str, object] = {}
        self._thread_id = str(uuid.uuid4())[:8]
        self._latest_rag_context = ""
        self._latest_rag_results: list[dict] = []
        self._trimmed = False
        self._round_count = 0
        self._cross_meeting = False

        builder = StateGraph(ChatState)
        builder.add_node("chat", self._chat_node)
        builder.add_edge(START, "chat")
        builder.add_edge("chat", END)
        self._graph = builder

    def set_meeting_context(
        self,
        transcript="",
        minutes="",
        action_items="",
        resolutions="",
        meeting_id=None,
        cross_meeting=False,
        meeting_ids=None,
    ):
        self._cross_meeting = cross_meeting
        if cross_meeting:
            self.meeting_context = {
                "transcript": "",
                "minutes": "",
                "action_items": "",
                "resolutions": "",
                "meeting_id": None,
                "meeting_ids": meeting_ids or [],
            }
            self._reset_memory_state(prefix="cross")
            return

        transcript = transcript or ""
        minutes = minutes or ""
        action_items = action_items or ""
        resolutions = resolutions or ""

        for name, value, limit in [
            ("transcript", transcript, self.MAX_TRANSCRIPT_LEN),
            ("minutes", minutes, self.MAX_MINUTES_LEN),
            ("action_items", action_items, self.MAX_ITEMS_LEN),
            ("resolutions", resolutions, self.MAX_ITEMS_LEN),
        ]:
            if len(value) > limit:
                logger.warning("ChatAgent context truncated: %s (%d -> %d)", name, len(value), limit)

        self.meeting_context = {
            "transcript": transcript[: self.MAX_TRANSCRIPT_LEN],
            "minutes": minutes[: self.MAX_MINUTES_LEN],
            "action_items": action_items[: self.MAX_ITEMS_LEN],
            "resolutions": resolutions[: self.MAX_ITEMS_LEN],
            "meeting_id": meeting_id,
            "meeting_ids": meeting_ids or [],
        }
        self._reset_memory_state(prefix=f"meeting_{meeting_id}")

    def _reset_memory_state(self, prefix: str):
        self._thread_id = f"{prefix}_{uuid.uuid4().hex[:8]}"
        self._trimmed = False
        self._round_count = 0
        self._latest_rag_context = ""
        self._latest_rag_results = []

    def chat(self, user_message: str) -> str:
        try:
            retriever = get_retriever()
            if self._cross_meeting:
                results = retriever.search(
                    user_message,
                    top_k=5,
                    meeting_ids=self.meeting_context.get("meeting_ids"),
                )
            else:
                results = retriever.search(
                    user_message,
                    top_k=5,
                    meeting_id=self.meeting_context.get("meeting_id"),
                )
            self._latest_rag_results = retriever.enrich_results(results)
            self._latest_rag_context = retriever.build_context(results=results) or "（暂无相关知识库内容）"
        except Exception as exc:
            logger.warning("RAG search failed: %s", exc)
            self._latest_rag_results = []
            self._latest_rag_context = "（暂无相关知识库内容）"

        app = self._graph.compile(checkpointer=self._checkpointer)
        result = app.invoke(
            {"messages": [HumanMessage(content=user_message)]},
            config={"configurable": {"thread_id": self._thread_id}},
        )
        response = result["messages"][-1].content or "抱歉，当前没有生成可用回复。"
        self._round_count += 1
        return response

    def get_memory_stats(self) -> dict:
        return {
            "round_count": self._round_count,
            "max_rounds": self.MAX_ROUNDS,
            "is_full": self._round_count >= self.MAX_ROUNDS,
            "trimmed": self._trimmed,
        }

    def get_latest_rag_results(self) -> list:
        return self._latest_rag_results

    @staticmethod
    def validate_input(user_input: str) -> str | None:
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
            "会议中提到的风险或问题有哪些？",
        ]

    def _build_system_prompt(self) -> str:
        if self._cross_meeting:
            return (
                "你是一个会议助手，负责从历史会议知识库中检索并回答问题。\n\n"
                "## 知识库召回结果\n"
                f"{self._latest_rag_context}\n\n"
                "回答规则：\n"
                "1. 根据召回内容回答，并尽量说明来自哪场会议。\n"
                "2. 如果需要跨会议对比，请分别引用各会议内容。\n"
                "3. 若知识库中没有足够信息，请明确说明，不要编造。\n"
                "4. 回答要简洁、准确。"
            )

        ctx = self.meeting_context
        return (
            "你正在回答单场会议问题。请优先根据当前会议内容回答，并在必要时结合 RAG 召回结果。\n\n"
            f"会议转录摘要：\n{ctx.get('transcript', '')}\n\n"
            f"会议纪要：\n{ctx.get('minutes', '')}\n\n"
            f"待办事项：\n{ctx.get('action_items', '')}\n\n"
            f"会议决议：\n{ctx.get('resolutions', '')}\n\n"
            "## 知识库召回结果\n"
            f"{self._latest_rag_context}\n\n"
            "回答规则：\n"
            "1. 优先依据当前会议内容回答。\n"
            "2. 如果当前会议信息不足，可参考召回片段并说明来源。\n"
            "3. 若没有足够依据，请明确说明，不要编造。\n"
            "4. 回答要简洁、准确。"
        )

    def _build_fallback_response(self) -> str:
        if self._latest_rag_results:
            snippets = []
            for item in self._latest_rag_results[:3]:
                meeting_title = item.get("meeting_title") or "当前会议"
                text = str(item.get("text") or "").strip().replace("\n", " ")
                if not text:
                    continue
                snippets.append(f"- {meeting_title}：{text[:120]}")
            if snippets:
                return "我先基于已检索到的会议内容给出参考：\n" + "\n".join(snippets)

        action_items = str(self.meeting_context.get("action_items") or "").strip()
        minutes = str(self.meeting_context.get("minutes") or "").strip()
        if action_items:
            return f"当前会话未能及时完成大模型生成，先返回会议中的待办信息供参考：\n{action_items[:300]}"
        if minutes:
            return f"当前会话未能及时完成大模型生成，先返回会议纪要摘要供参考：\n{minutes[:300]}"
        return "当前会话未能及时完成大模型生成，请稍后重试。"

    def _invoke_llm_with_timeout(self, messages: list) -> AIMessage:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.llm.invoke, messages)
        try:
            response = future.result(timeout=self.LLM_TIMEOUT_SECONDS)
            if isinstance(response, AIMessage):
                return response
            content = getattr(response, "content", None) or str(response)
            return AIMessage(content=content)
        except FutureTimeoutError:
            logger.warning("ChatAgent LLM invoke timed out after %ss", self.LLM_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.warning("ChatAgent LLM invoke failed: %s", exc)
        finally:
            # Do not wait for a blocked model call while serving the fallback response.
            executor.shutdown(wait=False, cancel_futures=True)

        return AIMessage(content=self._build_fallback_response())

    def _chat_node(self, state: ChatState, config):
        all_messages = list(state.get("messages", []))
        non_system = [message for message in all_messages if not isinstance(message, SystemMessage)]

        max_messages = self.MAX_ROUNDS * 2
        if len(non_system) > max_messages:
            non_system = non_system[-max_messages:]
            self._trimmed = True
            logger.info("ChatAgent sliding-window trim: keep latest %d messages", max_messages)

        llm_messages = [SystemMessage(content=self._build_system_prompt())] + non_system
        response = self._invoke_llm_with_timeout(llm_messages)
        return {"messages": [response]}
