"""
测试 ChatAgent 的 LangGraph Memory 机制:
  1. 轮次计数准确性
  2. 会议隔离（切换会议后 Memory 不串台）
  3. 10 轮滑窗裁剪
  4. LangGraph checkpoint 状态完整性
  5. 输入校验
"""

import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from agents.chat_agent import ChatAgent


def _make_mock_llm(response_text="Mock response"):
    """构造返回真实 AIMessage 的 mock LLM，兼容 LangGraph add_messages 的 reducer"""
    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content=response_text)
    return llm


class TestChatMemory(unittest.TestCase):

    def setUp(self):
        # 所有测试共享的 RAG mock
        self._rag_patcher = patch("agents.chat_agent.get_retriever")
        self._mock_get_retriever = self._rag_patcher.start()
        mock_retriever = MagicMock()
        mock_retriever.build_context.return_value = "mock rag context"
        self._mock_get_retriever.return_value = mock_retriever

    def tearDown(self):
        self._rag_patcher.stop()

    # ── 轮次计数 ──

    def test_round_count_increases(self):
        """5 轮对话后 round_count == 5，is_full == False"""
        agent = ChatAgent(llm=_make_mock_llm())
        agent.set_meeting_context(transcript="test", meeting_id=1)

        for i in range(5):
            agent.chat(f"Question {i}")

        stats = agent.get_memory_stats()
        self.assertEqual(stats["round_count"], 5)
        self.assertFalse(stats["is_full"])
        self.assertFalse(stats["trimmed"])

    def test_is_full_at_10_rounds(self):
        """第 10 轮时 is_full == True"""
        agent = ChatAgent(llm=_make_mock_llm())
        agent.set_meeting_context(transcript="test", meeting_id=1)

        for i in range(10):
            agent.chat(f"Question {i}")

        stats = agent.get_memory_stats()
        self.assertEqual(stats["round_count"], 10)
        self.assertTrue(stats["is_full"])

    # ── 会议隔离 ──

    def test_meeting_isolation(self):
        """切换会议后 round_count 重置为 1，不会累加"""
        agent = ChatAgent(llm=_make_mock_llm())

        # Meeting A: 3 轮
        agent.set_meeting_context(transcript="Meeting A", meeting_id=1)
        for i in range(3):
            agent.chat(f"A question {i}")
        self.assertEqual(agent.get_memory_stats()["round_count"], 3)

        # Meeting B: 1 轮 — 应重置
        agent.set_meeting_context(transcript="Meeting B", meeting_id=2)
        agent.chat("B question")
        stats = agent.get_memory_stats()
        self.assertEqual(stats["round_count"], 1)
        self.assertFalse(stats["trimmed"])

    # ── 10 轮滑窗裁剪 ──

    def test_sliding_window_triggers_trim(self):
        """第 11 轮触发裁剪，trimmed == True"""
        agent = ChatAgent(llm=_make_mock_llm())
        agent.set_meeting_context(transcript="test", meeting_id=1)

        for i in range(12):
            agent.chat(f"Question {i}")

        stats = agent.get_memory_stats()
        self.assertEqual(stats["round_count"], 12)
        self.assertTrue(stats["trimmed"])

    # ── LangGraph checkpoint 状态 ──

    def test_checkpoint_preserves_messages(self):
        """5 轮后 checkpoint 中至少包含 10 条非 system 消息"""
        agent = ChatAgent(llm=_make_mock_llm())
        agent.set_meeting_context(transcript="test transcript", meeting_id=1)

        for i in range(5):
            agent.chat(f"Question {i}")

        app = agent._graph.compile(checkpointer=agent._checkpointer)
        state = app.get_state(
            config={"configurable": {"thread_id": agent._thread_id}}
        )
        messages = state.values.get("messages", [])
        non_system = [
            m for m in messages if m.__class__.__name__ != "SystemMessage"
        ]
        self.assertGreaterEqual(len(non_system), 10)

    def test_thread_id_isolation(self):
        """不同 thread_id 对应独立的 checkpoint 快照"""
        agent = ChatAgent(llm=_make_mock_llm())
        app = agent._graph.compile(checkpointer=agent._checkpointer)

        # Thread A: 1 轮
        app.invoke(
            {"messages": [HumanMessage(content="A1")]},
            config={"configurable": {"thread_id": "thread_A"}},
        )

        # Thread B: 1 轮
        app.invoke(
            {"messages": [HumanMessage(content="B1")]},
            config={"configurable": {"thread_id": "thread_B"}},
        )

        state_a = app.get_state(config={"configurable": {"thread_id": "thread_A"}})
        state_b = app.get_state(config={"configurable": {"thread_id": "thread_B"}})

        msgs_a = [
            m for m in state_a.values.get("messages", [])
            if m.__class__.__name__ != "SystemMessage"
        ]
        msgs_b = [
            m for m in state_b.values.get("messages", [])
            if m.__class__.__name__ != "SystemMessage"
        ]

        # 各自独立，内容不同
        self.assertEqual(len(msgs_a), 2)
        self.assertEqual(len(msgs_b), 2)
        self.assertNotEqual(msgs_a[0].content, msgs_b[0].content)

    # ── 输入校验 ──

    def test_validate_empty_input(self):
        """空输入返回错误信息"""
        self.assertIsNotNone(ChatAgent.validate_input(""))
        self.assertIsNotNone(ChatAgent.validate_input("   "))

    def test_validate_too_long_input(self):
        """超过 500 字的输入返回错误信息"""
        long_msg = "x" * 501
        self.assertIsNotNone(ChatAgent.validate_input(long_msg))

    def test_validate_valid_input(self):
        """正常输入返回 None"""
        self.assertIsNone(ChatAgent.validate_input("这个会议的核心议题是什么？"))


if __name__ == "__main__":
    unittest.main()
