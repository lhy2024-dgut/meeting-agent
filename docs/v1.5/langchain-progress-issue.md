# LangChain 进展汇报 — @yhw028

> 分支：`feature/dev`
> 截止日期：2026-05-30

---

## 一、实现原理

### 1.1 为什么要迁移到 LangChain

项目最初使用 `demo/demo-lhy/` 中的手写代码直接调用 Ollama API，存在以下问题：

| 问题 | 手写代码 | LangChain 方案 |
|------|----------|----------------|
| Prompt 管理 | 字符串拼接，硬编码在函数里 | `ChatPromptTemplate` 模板化，支持变量注入 |
| 输出解析 | 手写正则 + `json.loads`，每种格式一套解析逻辑 | `BaseOutputParser` 统一接口，LCEL 自动串联 |
| 多轮对话 | `chat_messages` 列表手动维护，裁剪逻辑散落在调用方 | LangGraph `MemorySaver` checkpoint 机制，按 thread_id 自动隔离 |
| 模型切换 | 改代码 | 改一行配置 |
| 生态兼容 | 自己造轮子 | 复用 LangChain 生态的 retriever / embeddings 接口 |

### 1.2 核心设计：LCEL 管道

LCEL（LangChain Expression Language）用 `|` 管道符串联组件，数据从左往右流：

```
Prompt Template  →  LLM  →  Output Parser
     |                |           |
  填充变量        调用模型     结构化解析
```

**纪要生成链**（`chains/minutes_chain.py`）：

```python
chain = MINUTES_PROMPT | self.llm   # LCEL 管道
raw = chain.invoke({"transcript": ..., "title": ..., "date": ...})
action, resolutions, minutes = self.parser.parse(raw_text)
```

**对话链**（`agents/chat_agent.py`）：

```python
# LangGraph StateGraph 包装 LLM 调用
builder = StateGraph(ChatState)
builder.add_node("chat", self._chat_node)  # node 内部调用 LLM
builder.add_edge(START, "chat")
builder.add_edge("chat", END)
app = builder.compile(checkpointer=MemorySaver())
result = app.invoke({"messages": [HumanMessage(...)]}, config={"thread_id": ...})
```

### 1.3 用到的 LangChain / LangGraph 组件

| 组件 | 来源 | 作用 |
|------|------|------|
| `BaseChatModel` | `langchain_core` | 自定义 LLM 的基类，实现 `_generate` / `_stream` |
| `ChatPromptTemplate` | `langchain_core` | Prompt 模板，支持 `system` / `human` / `MessagesPlaceholder` |
| `MessagesPlaceholder` | `langchain_core` | 在 Prompt 中插入历史对话列表 |
| `BaseOutputParser` | `langchain_core` | 自定义输出解析器基类 |
| `StateGraph` | `langgraph` | 定义对话状态机，承载 checkpoint |
| `MemorySaver` | `langgraph` | 内存态 checkpoint，按 thread_id 隔离对话状态 |
| `HumanMessage` / `AIMessage` / `SystemMessage` | `langchain_core` | 统一的消息类型 |
| `Embeddings` | `langchain_core` | 自定义 embedding 的基类 |

**没有使用** `langchain-ollama`（`ChatOllama`），因为该包存在解析 bug（参见 `engines/llm.py` 注释）。直接用 `ollama` 库封装了 `OllamaChatModel`，继承 `BaseChatModel`，兼容 LCEL 管道。

---

## 二、代码结构变化

### 2.1 新增文件

| 文件 | 说明 |
|------|------|
| `agents/chat_agent.py` | LangGraph 多轮对话 Agent，核心模块 |
| `chains/minutes_chain.py` | LCEL 纪要生成链，含 LRU 缓存 + retry |
| `chains/export_chain.py` | 文档导出链（docx / md / pdf） |
| `prompts/templates.py` | ChatPromptTemplate 定义（MINUTES_PROMPT / CHAT_PROMPT） |
| `prompts/templates/auto_summary.yaml` | 摘要生成的 YAML Prompt 模板 |
| `rag/retriever.py` | PGVector RAG 检索器，覆盖式索引 |
| `rag/embeddings.py` | Ollama Embedding 封装（BGE-M3） |
| `rag/text_splitter.py` | 自研文本分块器（替代 langchain_text_splitters） |
| `engines/llm.py` | OllamaChatModel，继承 BaseChatModel |
| `engines/asr_engine.py` | Faster-Whisper ASR 引擎 |
| `db/models.py` | SQLAlchemy ORM 模型（Meeting / Transcription / MeetingChunk） |
| `db/repository.py` | 数据仓库层 |
| `db/engine.py` | 数据库引擎 + pgvector 适配 |
| `services/meeting_service.py` | 会议处理全流程编排 |
| `services/file_service.py` | 文件上传/存储 |
| `ui/` 目录全部文件 | Streamlit 前端页面 |
| `tests/test_chat_memory.py` | 11 个 ChatAgent 测试用例 |
| `tests/eval_chat_memory.py` | 语义连续性评估脚本 |
| `docs/v1.5/chat-memory-design.md` | Memory 方案设计决策文档 |
| `storage/migrations/` | Alembic 数据库迁移脚本 |

### 2.2 修改的文件

| 文件 | 变化 |
|------|------|
| `config.py` | 新增 LLM / ASR / RAG / DB 配置项 |
| `main.py` | CLI 入口，新增 transcribe / live / minutes / export / chat / history 命令 |
| `app.py` | Streamlit 入口，多页面路由 |
| `requirements.txt` | 新增 langchain-core / langgraph / pgvector / faster-whisper 等依赖 |

### 2.3 未改动的文件

| 文件 | 说明 |
|------|------|
| `demo/demo-lhy/` | 旧版 demo，未修改，作为参考保留 |
| `templates/` | 导出模板目录，未改动 |
| `modules/` | 旧模块目录，未改动 |

---

## 三、本地运行方式

### 3.1 环境要求

- Python 3.11+
- PostgreSQL 15+（需安装 pgvector 扩展）
- Ollama（本地 LLM 服务）
- FFmpeg（音频处理）

### 3.2 安装依赖

```bash
# 切换到开发分支
git checkout feature/dev

# 安装依赖
pip install -r requirements.txt
```

新增的关键依赖：
- `langchain-core` — LangChain 核心
- `langgraph` — 状态图 + checkpoint
- `faster-whisper` — 语音识别
- `pgvector` — PostgreSQL 向量扩展
- `sqlalchemy` + `psycopg2-binary` — ORM
- `alembic` — 数据库迁移
- `ollama` — LLM 客户端

### 3.3 配置

复制 `.env.example` 为 `.env`，填写数据库密码：

```bash
cp .env.example .env
```

关键环境变量：
- `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASS` — PostgreSQL 连接
- `OLLAMA_BASE_URL` — Ollama 服务地址（默认 `http://localhost:11434`）
- `LLM_MODEL` — LLM 模型名（默认 `qwen3.5:4b`）
- `EMBEDDING_MODEL` — Embedding 模型名（默认 `bge-m3`）

### 3.4 拉取模型

```bash
ollama pull qwen3.5:4b
ollama pull bge-m3
```

### 3.5 数据库迁移

```bash
alembic upgrade head
```

### 3.6 启动

```bash
# Streamlit 前端
streamlit run app.py

# 或 CLI 模式
python main.py minutes <audio_path>
python main.py chat <meeting_id>
```

---

## 四、当前效果

### 4.1 已实现功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 语音转写 | ✅ | Faster-Whisper 本地 ASR，支持流式输出 |
| 纪要生成 | ✅ | LCEL 管道，提取待办/决议/纪要三部分 |
| 多轮对话 | ✅ | LangGraph MemorySaver，10 轮滑窗，会议隔离 |
| RAG 知识库 | ✅ | PGVector 覆盖式索引，跨会议检索 |
| 历史会议 | ✅ | 分页列表 + 摘要 + 项目名 + 搜索 |
| 文档导出 | ✅ | docx / md / pdf 三格式 |
| 摘要自动生成 | ✅ | LLM 生成 short_summary + project_name，双层 fallback |

### 4.2 测试覆盖

`tests/test_chat_memory.py` — 11 个用例，覆盖 6 个维度：

| 维度 | 用例 | 状态 |
|------|------|------|
| 轮次计数 | 5 轮后 count=5, is_full=False | ✅ |
| 满窗口标记 | 10 轮后 is_full=True | ✅ |
| 会议隔离 | 切换会议后 count 重置 | ✅ |
| 滑窗裁剪 | 12 轮后 trimmed=True | ✅ |
| checkpoint 完整性 | 5 轮后 checkpoint 含 ≥10 条消息 | ✅ |
| thread_id 隔离 | 不同 thread 独立快照 | ✅ |
| 语义连续性 | 第 10 轮仍包含第 1 轮输入 | ✅ |
| 裁剪正确性 | 第 11 轮移除第 1 轮消息 | ✅ |
| 输入校验 | 空输入 / 超长输入 / 正常输入 | ✅ |

### 4.3 还存在的问题

1. **Memory 不持久化** — `MemorySaver` 存于内存，Streamlit 重启后对话历史丢失
2. **纪要质量依赖模型能力** — 4B 小模型对长文本（>8000 字符）的纪要生成不稳定，需要 retry + fallback
3. **同会议两个页面对话不互通** — `ui/chat.py` 和 `ui/result.py` 各自维护独立的 ChatAgent 实例

---

## 五、遇到的问题

### 问题 1：pgvector 0.8.1 不兼容 PostgreSQL 18

**复现**：Windows 11 + PostgreSQL 18 + `pip install pgvector`，导入时报 ABI 不兼容错误

**报错信息**：
```
pgvector.psycopg2 requires pgvector >= 0.8.2 but installed 0.8.1
```

**已尝试**：
- `pip install pgvector --upgrade` → 无更高版本 wheel
- 降级 PostgreSQL → 不现实

**当前状态**：✅ 已解决
**解决方案**：安装 VS Build Tools + nmake，从源码编译 pgvector 0.8.2

---

### 问题 2：`langchain-ollama` 的 `ChatOllama` 解析 bug

**复现**：使用 `ChatOllama` 调用 Ollama 时，部分模型返回格式解析失败

**报错信息**：
```
langchain_ollama.chat_models.ChatOllama: Error parsing response
```

**已尝试**：
- 降级 `langchain-ollama` 版本 → 不同版本 bug 不同
- 调整模型参数 → 无法根治

**当前状态**：✅ 已解决
**解决方案**：绕过 `langchain-ollama`，直接用 `ollama` 库封装 `OllamaChatModel`（继承 `BaseChatModel`），手动实现 `_generate` / `_stream` / `_convert_messages`

---

### 问题 3：`langchain_text_splitters` 触发 transformers/onnxruntime 崩溃

**复现**：`from langchain_text_splitters import RecursiveCharacterTextSplitter` 导入时触发 transformers 依赖链

**报错信息**：
```
ImportError: cannot import name 'onnxruntime' ...
```

**已尝试**：
- `pip install onnxruntime` → 版本冲突
- 指定 transformers 版本 → 与其他依赖冲突

**当前状态**：✅ 已解决
**解决方案**：自研 `SimpleTextSplitter`（`rag/text_splitter.py`），基于正则递归分割 + 长度合并，中文友好，无外部依赖

---

### 问题 4：SQLAlchemy `text()` 中 tuple 参数绑定

**复现**：用 `text("WHERE id IN :ids")` + `{"ids": (1,2,3)}` 执行查询

**报错信息**：
```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.SyntaxError) operator does not exist: integer = record
```

**已尝试**：
- `IN :ids` → tuple 不展开，被当成 record 比较
- 拼接 SQL 字符串 → SQL 注入风险

**当前状态**：✅ 已解决
**解决方案**：改用 `WHERE id = ANY(:ids)`，PostgreSQL 的 `ANY` 接受数组参数，SQLAlchemy 正确绑定

---

### 问题 5：Streamlit session_state 与 LangChain Memory 冲突

**复现**：`ConversationBufferWindowMemory` 存入 `st.session_state` 后，切换会议时清空和重建顺序不可靠，导致对话串台

**报错信息**：无明确报错，但用户在会议 B 问答时看到会议 A 的上下文

**已尝试**：
- 手动 `memory.clear()` → Streamlit rerun 时序问题，clear 和 set 顺序不确定
- 用 `session_id` 做 key 管理 → 仍然依赖"记得清空"

**当前状态**：✅ 已解决
**解决方案**：放弃 `ConversationBufferWindowMemory`，改用 LangGraph `MemorySaver`。每个会议分配独立 `thread_id`（`meeting_{id}_{uuid}`），新 thread 天然无旧数据，隔离不依赖"记得清空"。详见 `docs/v1.5/chat-memory-design.md`

---

### 问题 6：`add_messages` reducer 的去重陷阱

**复现**：用户连续问两次相同问题，第二条 HumanMessage 被静默丢弃

**原因**：LangGraph 默认的 `add_messages` reducer 按消息 ID 做 upsert 合并，相同内容的消息被视为重复

**当前状态**：✅ 已解决
**解决方案**：自定义 `ChatState`，用 `operator.add` 替代 `add_messages`：

```python
class ChatState(TypedDict):
    messages: Annotated[list, operator.add]  # 纯追加，不去重
```

---

## 六、希望讨论会解决的问题

### 1. RAG 检索召回率如何评估和提升

**当前状态**：RAG 模块已实现完整流程（分块 → embedding → PGVector 检索），但没有量化评估，不知道召回率是多少。

**行业参考**：生产环境 RAG 的 Recall@5 一般在 70-90%，低于 70% 说明 embedding 或 chunk 策略有问题。现在的chunk策略有点太粗暴了。

**想讨论的点**：
- **评估方法**：是用项目自身会议数据人工标注 10-20 个 QA 对做本地评估，？
- **评估指标**：计划用 Recall@5 + MRR，够不够？
- **召回率低的话优先调什么**：chunk_size（当前 512，对中文偏小）、换 embedding 模型、还是加混合检索（向量 + BM25）？

### 2. Embedding 模型选型

**当前**：`bge-m3`（Ollama 本地，1024 维），多语言模型。

**想讨论的点**：
- bge-m3 在中文会议场景下，是否不如专门的中文模型（如 `bge-large-zh-v1.5`）？
- 1024 维对检索速度和存储的影响——会议量到数百场时是否需要降维？
- 批量索引场景（一次性导入大量会议）本地 embedding 太慢，是否需要引入 embedding API？
