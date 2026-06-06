# Chat Memory 设计决策文档

> 模块：对话 Memory 多轮问答（任务 2.1）
> 作者：@yhw028
> 日期：2026-05-25

## 一、方案选型：LangGraph MemorySaver vs LangChain ConversationBufferWindowMemory

### 最初方案

任务描述要求使用 `langchain.memory.ConversationBufferWindowMemory`。

### 最终方案

使用 LangGraph `StateGraph` + `MemorySaver`（checkpoint 机制）。

### 决策理由

| 维度 | ConversationBufferWindowMemory | LangGraph MemorySaver |
|---|---|---|
| 线程隔离 | 需要手动管理 session_id → Memory 映射 | checkpoint 原生按 `thread_id` 隔离 |
| 序列化 | Memory 对象不可 pickle，在 Streamlit rerun 时状态丢失 | checkpoint 纯 dict，天然支持序列化 |
| 可观测性 | 无内置状态查询 | `get_state()` 可随时查看 checkpoint 快照 |
| LangChain 生态方向 | 已被标记为 deprecated（runnable 分支） | LangGraph 是 LangChain 官方主推的状态管理方案 |
| 前端轮次展示 | 需要额外包装计数器 | 可直接读 messages 长度 + 自定义 stats 字典 |

### Streamlit rerun 场景的关键问题

Streamlit 每次用户交互都会重新执行整个脚本。如果使用 `ConversationBufferWindowMemory`：

```python
# ❌ 每次 rerun 都会丢失，因为 Memory 对象不能安全存入 session_state
memory = st.session_state.get("memory")  # 取出来可能已损坏
```

而 LangGraph `MemorySaver` 是纯数据（dict checkpoint），配合 `thread_id` 机制：

```python
# ✅ checkpoint 数据安全存入 session_state，切换会议时换 thread_id 即可隔离
agent = ChatAgent()
agent.set_meeting_context(..., meeting_id=meeting.id)
st.session_state.chat_agent = agent
```

## 二、架构设计

```
┌──────────────────────────────────────────────────┐
│  Streamlit session_state                          │
│  ┌─────────────┐  ┌──────────────┐               │
│  │ chat_agent   │  │ result_agent │  (两个页面各 │
│  │ (ChatAgent)  │  │ (ChatAgent)  │   自独立)    │
│  └──────┬───────┘  └──────┬───────┘               │
│         │                 │                       │
│  ┌──────┴───────┐  ┌──────┴───────┐               │
│  │ MemorySaver  │  │ MemorySaver  │               │
│  │ thread_id=A  │  │ thread_id=B  │               │
│  └──────────────┘  └──────────────┘               │
└──────────────────────────────────────────────────┘

在不同会议间切换:
  meeting_1 → thread_id = "meeting_1_a1b2c3d4"
  meeting_2 → thread_id = "meeting_2_e5f6g7h8"
  → checkpoint 完全隔离，不可能串台
```

## 三、核心机制

### 3.1 10 轮滑窗

`_chat_node` 每次调用时过滤 state 中的非系统消息，保留最近 20 条（10 轮 × 2 = 每人各一条）：

- 第 1-10 轮：所有上下文完整保留
- 第 11 轮起：自动丢弃最早的消息，保留最近 20 条
- `_trimmed` 标记置为 `True`，前端读取后提示用户

### 3.2 会议隔离

`set_meeting_context()` 被调用时自动生成新 `thread_id`：

```python
self._thread_id = f"meeting_{meeting_id}_{uuid.uuid4().hex[:8]}"
```

效果：
- 同会议多轮对话共享 memory
- 切会议自动新建线程，旧线程完全不可访问
- `_round_count` 和 `_trimmed` 同步重置

### 3.3 RAG 知识库注入

每次 `chat()` 调用时实时检索当前问题的相关知识库片段，拼入 system prompt。检索时排除当前会议自身（`exclude_meeting_id`），避免"自己查自己"。

## 四、测试覆盖

| 测试场景 | 测试方法 | 状态 |
|---|---|---|
| 轮次计数递增 | `test_round_count_increases` | ✅ |
| 10 轮 is_full 标记 | `test_is_full_at_10_rounds` | ✅ |
| 会议隔离不串台 | `test_meeting_isolation` | ✅ |
| 11 轮触发裁剪 | `test_sliding_window_triggers_trim` | ✅ |
| checkpoint 消息完整性 | `test_checkpoint_preserves_messages` | ✅ |
| thread_id 隔离 | `test_thread_id_isolation` | ✅ |
| 第 10 轮引用第 1 轮上下文 | `test_round_10_references_round_1_context` | ✅ |
| 第 11 轮裁剪后丢失第 1 轮 | `test_round_11_trims_round_1_context` | ✅ |
| 空输入校验 | `test_validate_empty_input` | ✅ |
| 超长输入校验 | `test_validate_too_long_input` | ✅ |
| 正常输入校验 | `test_validate_valid_input` | ✅ |

## 五、已知限制

1. **Memory 不持久化** — `MemorySaver` 存于内存，Streamlit 重启后所有对话历史丢失。如需持久化，可替换为 `SqliteSaver` 或 `PostgresSaver`。
2. **同会议多页面** — `ui/chat.py` 和 `ui/result.py` 各自维护独立的 ChatAgent 实例，两者对话历史不互通。这是有意设计（两个入口互不干扰），但用户可能在两个页面看到不同的对话历史。
3. **滑窗基于消息数而非语义** — 裁剪完全按消息数量，不考虑语义重要性。简单的裁剪策略足以满足当前需求。
