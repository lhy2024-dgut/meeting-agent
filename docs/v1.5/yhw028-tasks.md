# V1.5 个人任务汇报 — yhw028

## 任务总览

| 编号 | 任务 | 状态 |
|---|---|---|
| 2.1 | LangChain Memory 多轮对话 | 已完成 |
| 2.2 | 自定义问题问答 | 已完成 |
| 2.3 | 历史会议列表与摘要查询 | 已完成 |
| — | Route A RAG 索引重构（计划外） | 已完成 |
| — | 跨会议 RAG 检索（计划外） | 已完成 |

---

## 2.1 · 多轮对话 Memory

### 方案

**技术选型：LangGraph StateGraph + MemorySaver 替代 ConversationBufferWindowMemory**

任务单要求 `ConversationBufferWindowMemory`，实际选了 LangGraph。原因：Streamlit 的 `session_state` 是 key-value 生命周期，`ConversationBufferWindowMemory` 依赖 LangChain 内部 session 管理，两个 session 模型打架。切换会议时需要"先清空再重建"，Streamlit rerun 模型下清空和重建的顺序不可靠，串台不是可能而是迟早。

LangGraph MemorySaver 用 checkpoint 做隔离：每个会议分配独立 `thread_id`，新 thread 天然无旧数据，隔离不依赖"记得清空"。

### 架构

```
ChatState (operator.add 拼接消息)
  └── StateGraph (单 node: _chat_node)
        └── MemorySaver (checkpoint 按 thread_id 隔离)
```

**State 设计**：用 `operator.add` 而非 LangChain 默认的 `add_messages` reducer。`add_messages` 会按消息 ID 做 upsert 合并，同一问题问两次会被静默去重。`operator.add` 是纯追加，行为可预测。

**Graph 设计**：单 node 的 trivial graph（START → chat → END）。Graph 本身不做事，作用是承载 checkpoint —— 没有 graph 包装就不能用 MemorySaver。

**Node 逻辑**（每次 invoke 执行）：
1. 重新生成 system prompt（注入最新 RAG 检索结果，不缓存）
2. 滑窗裁剪：非 system 消息超过 20 条（10 对 QA）时保留最近 20 条
3. 调用 LLM

SystemMessage 每次放在消息列表最前面传入 LLM，不存入 checkpoint。因为 system prompt 包含会议上下文和 RAG 结果，每次可能不同，存入 checkpoint 会污染裁剪逻辑。

### 会议隔离

`set_meeting_context()` 每次生成新 `thread_id`，同时重置 `round_count`、`trimmed`、RAG 结果。隔离是两层的：
- **checkpoint 层**：不同 thread_id 在 MemorySaver 中完全隔离
- **计数层**：业务层面的 round_count 也归零

### 前端

`get_memory_stats()` 暴露 `round_count` / `is_full` / `trimmed`，chat 页和 result 页都展示了轮次计数和裁剪提示。

### 测试

11 个用例覆盖 6 个维度。最关键的语义连续性测试用 spy LLM（记录每次 invoke 收到的完整消息列表）而非 mock，验证第 10 轮消息列表中仍包含第 1 轮输入，第 11 轮已移除。

---

## 2.2 · 自定义问题问答

### 方案

改动量最小的任务。chat_agent 已有 `chat()` 方法，主要做兜底：

**输入校验**：`validate_input()` 静态方法，空输入和 >500 字在进 agent 前拦截，返回错误文案。两处 UI（chat 页和 result 页）走同一校验函数。

**异常兜底**：try/except 包裹整个 RAG + LLM 链路，任何环节失败返回中文提示而非堆栈。

---

## 2.3 · 历史会议列表与摘要查询

### 方案

分三层实现：

**数据层** — `meetings` 表新增 `short_summary` VARCHAR(500) + `project_name` VARCHAR(255)，均为 nullable，旧数据兼容。Alembic migration 而非手写 SQL。

**生成层** — 在 `meeting_service.py` 的 Step 4（LLM 纪要）和 Step 5（持久化）之间插入 Step 4.5，调用 LLM 生成摘要和项目名。独立的 `auto_summary.yaml` 模板，LLM 返回 JSON。**双层 fallback**：模板加载失败 → `minutes[:200]`；JSON 解析失败 → 同上。这一步失败不阻塞主流程。

**展示层** — `history.py` 分页 10 条、倒序排列、卡片展示。搜索从纯标题扩展为 title + short_summary + project_name 三字段 OR。项目名支持内联编辑。旧数据无 summary 时自动截断纪要前 150 字。

---

## Route A · RAG 索引重构（计划外）

### 问题

旧 `index_meeting()` 是追加式 INSERT。同一 meeting 重试导致 chunk 无限膨胀，RAG 检索结果被同一场会议的旧版本 chunk 污染。

### 方案

**核心思路：覆盖式重建**。新增 `rebuild_meeting_index()`，事务内 `DELETE FROM meeting_chunks WHERE meeting_id = :mid` + 重新 `INSERT`。embedding 计算放在事务外，避免长事务。

**顺手做的增强**：
- 结构化 chunk：分 chunk_type（transcript / minutes / action_item / resolution）做 source tagging
- content_hash：SHA256 去重 + 应用层按 `(chunk_type, content_hash)` 合并
- 去重后按 chunk_type 重新编号 chunk_index
- 空文本时清空旧索引（覆盖式语义一致）
- 数据库层兜底：`UNIQUE(meeting_id, chunk_type, chunk_index)` + 复合索引

### 检索增强

`search()` 从 4 分支 if-else 重构为动态 WHERE 子句，支持组合过滤：

| 调用方式 | 效果 |
|---|---|
| `search(query)` | 全库检索 |
| `search(query, meeting_id=5)` | 仅会议 5 |
| `search(query, meeting_ids=[3,5,8])` | 多会议定向 |
| `search(query, exclude_meeting_id=5)` | 排除当前会议 |
| `search(query, meeting_ids=[3,5], chunk_type="resolution")` | 组合过滤 |

`= ANY(:ids)` 替代 `IN :ids`，解决 SQLAlchemy `text()` 中 tuple 参数绑定的兼容性问题。

---

## 跨会议 RAG 检索（计划外）

### 方案

**当前策略**：chat_agent 用 `exclude_meeting_id=当前会议`，当前会议上下文直接从 meeting_context 注入 prompt，历史会议走 RAG。

### 核心改动

**上下文可读化**：`build_context()` 输出从 `[minutes#0 | meeting=12 | score=0.812]` 变为 `[《Q3预算评审会》| 纪要 | 相似度 0.81]`。join meetings 表取标题，中文类型标签。

**消除双检索**：`search()` → `enrich_results()` → `build_context(results=results)`。build_context 接受预取 results 参数，避免重复 embedding + 向量查询。

**结构化结果**：`enrich_results()` 给每条结果补 `meeting_title` + `chunk_type_label`，前端通过 `get_latest_rag_results()` 直接消费。

**Prompt 规则**：system prompt 明确 4 条优先级 —— 当前会议优先 → 历史辅助需标注来源 → 无依据不编造 → 准确简洁。

### 检索模式速查

```
search(query)                              → 全库
search(query, meeting_id=5)                → 单会议
search(query, meeting_ids=[3,5,8])         → 多会议定向
search(query, exclude_meeting_id=5)        → 排除当前（默认策略）
search(query, meeting_ids=[3,5], chunk_type="resolution")  → 组合
```

---

## 数据库变更汇总

| 表 | 新增字段 | 迁移 |
|---|---|---|
| `meetings` | `short_summary` VARCHAR(500), `project_name` VARCHAR(255) | `a1b2c3d4e5f6` |
| `meeting_chunks` | `chunk_type` VARCHAR(32), `chunk_index` INTEGER, `content_hash` VARCHAR(64), `created_at` DATETIME | `86cee12a749a` |
| `meeting_chunks` | 复合索引 + content_hash 索引 | `662a20a42c74` |
| `meeting_chunks` | UNIQUE(meeting_id, chunk_type, chunk_index) | `5ebf9e3a9002` |

---

## 关键踩坑

| 坑 | 解法 |
|---|---|
| pgvector 0.8.1 不兼容 PG18 | VS Build Tools + nmake 从源码编译 0.8.2 |
| `pgvector.Vector` vs `pgvector.sqlalchemy.Vector` 类型混淆 | 检索用 `from pgvector import Vector`，模型定义用 `from pgvector.sqlalchemy import Vector` |
| SQLAlchemy `text` 被变量名覆盖 | `for text in texts` → `for doc in docs` |
| `IN :param` tuple 不展开 | `WHERE id = ANY(:ids)` |
| server_default 导致 UNIQUE 约束失败 | 加约束前 `DELETE WHERE chunk_type='unknown'` |
| f-string 中文引号解析错误 | 外层换单引号：`f'"未在历史..."'` |
