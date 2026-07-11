"""
测试 ChatAgent 的 LangGraph Memory 机制:
  1. 轮次计数准确性
  2. 会议隔离（切换会议后 Memory 不串台）
  3. 10 轮滑窗裁剪
  4. LangGraph checkpoint 状态完整性
  5. 输入校验
  6. 语义连续性（第 10 轮仍能引用第 1 轮的上下文）
"""

import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.chat_agent import ChatAgent


def _make_mock_llm(response_text="Mock response"):
    """构造返回真实 AIMessage 的 mock LLM，兼容 LangGraph add_messages 的 reducer"""
    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content=response_text)
    return llm


def _make_spy_llm():
    """构造 spy LLM，捕获每次 invoke 收到的 messages，便于验证上下文连续性"""
    llm = MagicMock()
    llm.invoke_call_args = []

    def _invoke_side_effect(messages):
        llm.invoke_call_args.append(messages)
        return AIMessage(content="Mock response")

    llm.invoke.side_effect = _invoke_side_effect
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

    # ── 语义连续性：第 10 轮仍能引用第 1 轮上下文 ──

    def test_round_10_references_round_1_context(self):
        """第 10 轮调用 LLM 时，消息列表中仍包含第 1 轮的用户输入"""
        spy_llm = _make_spy_llm()
        agent = ChatAgent(llm=spy_llm)
        agent.set_meeting_context(transcript="关于Q3预算的讨论", meeting_id=100)

        round_1_question = "Q1: 我叫张三，我的工号是9527"
        agent.chat(round_1_question)

        for i in range(2, 11):
            agent.chat(f"Q{i}: 继续讨论预算问题")

        # 第 10 轮（共 20 条非系统消息，尚未触发裁剪）调用 LLM 时传入的 messages
        msgs_round_10 = spy_llm.invoke_call_args[-1]

        # 过滤出非系统消息
        non_system = [m for m in msgs_round_10 if not isinstance(m, SystemMessage)]

        # 第 1 轮的 HumanMessage 仍在列表中
        first_round_texts = [m.content for m in non_system if isinstance(m, HumanMessage)]
        self.assertIn(round_1_question, first_round_texts,
                      "第 10 轮时第 1 轮的用户问题应该在上下文中")

        # 第 10 轮处理时 state 中已有 19 条非系统消息
        # （10 条 Human + 9 条 AI，第 10 轮 AI 尚未生成）
        self.assertEqual(len(non_system), 19,
                         f"第 10 轮应有 19 条非系统消息，实际 {len(non_system)}")

        stats = agent.get_memory_stats()
        self.assertEqual(stats["round_count"], 10)
        self.assertFalse(stats["trimmed"],
                         "第 10 轮不应触发裁剪（恰好满窗口）")

    def test_round_11_trims_round_1_context(self):
        """第 11 轮触发裁剪后，第 1 轮的消息被移除"""
        spy_llm = _make_spy_llm()
        agent = ChatAgent(llm=spy_llm)
        agent.set_meeting_context(transcript="关于Q3预算的讨论", meeting_id=101)

        round_1_question = "Q1: 我叫张三，我的工号是9527"
        agent.chat(round_1_question)

        for i in range(2, 12):  # 2..11, 共 10 轮
            agent.chat(f"Q{i}: 继续讨论预算问题")

        # 第 11 轮触发了裁剪
        self.assertTrue(agent.get_memory_stats()["trimmed"])

        # 第 11 轮调用 LLM 时传入的 messages
        msgs_round_11 = spy_llm.invoke_call_args[-1]
        non_system = [m for m in msgs_round_11 if not isinstance(m, SystemMessage)]

        # 裁剪后应保留最近 20 条，第 1 轮的消息已被移除
        first_round_texts = [m.content for m in non_system if isinstance(m, HumanMessage)]
        self.assertNotIn(round_1_question, first_round_texts,
                         "第 11 轮裁剪后第 1 轮的问题应该已被移除")

        # 保留 20 条非系统消息
        self.assertEqual(len(non_system), 20,
                         f"裁剪后应保留 20 条，实际 {len(non_system)}")


if __name__ == "__main__":
    unittest.main()
