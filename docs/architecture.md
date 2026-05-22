# Meeting Agent 架构与功能说明

## 1. 项目概述

Meeting Agent 是一个本地运行的 AI 会议纪要系统。输入音频或视频文件，自动完成语音转写、纪要提取、待办/决议生成、RAG 知识库索引和文档导出。

核心特点：全部 AI 能力本地运行（Ollama + Faster-Whisper），无需云端 API。

---

## 2. 架构分层

```
┌─────────────────────────────────────────────────┐
│  入口层                                           │
│  app.py (Streamlit Web) / main.py (CLI 命令行)    │
├─────────────────────────────────────────────────┤
│  UI 层 (ui/)                                      │
│  home / upload / result / chat / history / stats  │
├─────────────────────────────────────────────────┤
│  服务层 (services/)                               │
│  MeetingService — 7步处理流水线                    │
│  FileService    — 文件上传/哈希/存储/格式转换      │
├─────────────────────────────────────────────────┤
│  链路层 (chains/)                                  │
│  MinutesChain  — 文本 → 纪要/待办/决议            │
│  ExportChain   — 导出 DOCX / MD / PDF             │
├─────────────────────────────────────────────────┤
│  Agent 层 (agents/)                                │
│  ChatAgent     — RAG 检索 + 多轮对话问答          │
├─────────────────────────────────────────────────┤
│  引擎层 (engines/)                                 │
│  ASREngine     — Faster-Whisper 语音识别          │
│  AudioUtils    — 音频格式转换 + 视频抽音轨         │
│  PDFEngine     — PDF 生成（PyMuPDF + pypdf）      │
├─────────────────────────────────────────────────┤
│  RAG 层 (rag/)                                     │
│  向量化 → 分块 → FAISS 索引 → 相似度检索          │
├─────────────────────────────────────────────────┤
│  数据层 (db/)                                      │
│  SQLAlchemy ORM + Repository (CRUD)               │
└─────────────────────────────────────────────────┘
```

---

## 3. 技术栈

| 层级       | 技术                                      | 说明                          |
|-----------|------------------------------------------|------------------------------|
| 前端       | Streamlit                                | Web UI 框架                   |
| LLM       | Ollama + qwen3.5:4b                     | 本地大模型，纪要生成 & 问答     |
| Embedding | Ollama + bge-m3                          | 文本向量化，驱动 RAG           |
| ASR       | Faster-Whisper (base, CPU, INT8量化)     | 本地语音识别                   |
| RAG       | FAISS + LangChain                       | 向量检索，会议内容可问答       |
| 数据库     | PostgreSQL + SQLAlchemy                  | 持久化会议数据和转写文本       |
| 导出       | python-docx / PyMuPDF / pypdf           | DOCX / PDF / MD 三种格式      |
| 可视化     | Plotly                                   | 统计图表                      |
| 编排       | LangChain (Chains + ChatHistory)         | LLM 调用链 + 多轮对话管理      |

---

## 4. 数据库表设计

### 4.1 meetings 表

| 字段               | 类型          | 说明                          |
|-------------------|---------------|------------------------------|
| id                | INTEGER (PK)  | 自增主键                      |
| title             | VARCHAR(255)  | 会议标题（必填）               |
| created_at        | DATETIME      | 创建时间                      |
| updated_at        | DATETIME      | 更新时间                      |
| audio_path        | VARCHAR(500)  | 音频/视频文件存储路径          |
| duration_category | VARCHAR(50)   | 时长分类: short/medium/long   |
| environment       | VARCHAR(100)  | 会议环境: quiet/noisy/multi_speaker |
| file_hash         | VARCHAR(64)   | 文件 SHA256 哈希（索引，用于缓存去重）|
| minutes_text      | TEXT          | 会议纪要正文（Markdown）       |
| action_items_text | TEXT          | 待办事项列表                  |
| resolutions_text  | TEXT          | 会议决议列表                  |

### 4.2 transcriptions 表

| 字段          | 类型          | 说明                          |
|--------------|---------------|------------------------------|
| id           | INTEGER (PK)  | 自增主键                      |
| meeting_id   | INTEGER (FK)  | 关联 meetings.id，级联删除    |
| text         | TEXT          | 转录文本片段                   |
| timestamp    | FLOAT         | 时间戳                        |
| start_time   | FLOAT         | 片段开始时间（秒）             |
| end_time     | FLOAT         | 片段结束时间（秒）             |
| audio_segment| VARCHAR(500)  | 音频片段路径                   |
| summary      | TEXT          | 片段摘要                       |

### 4.3 表关系

```
meetings (1) ──< (N) transcriptions
  ↑                      ↑
  │  meeting_id FK       │
  └──────────────────────┘
```

---

## 5. 当前版本功能清单

### 5.1 核心处理流水线（7步）

| 步骤 | 阶段           | 说明                               |
|-----|---------------|-----------------------------------|
| 1   | 缓存检查       | 按文件 SHA256 哈希查重，相同文件跳过 ASR  |
| 2   | 语音识别       | Faster-Whisper 转写音频为带时间戳文本段 |
| 3   | 会议分类       | 启发式分析：时长分短/中/长，环境分安静/嘈杂/多人 |
| 4   | LLM 提取       | qwen3.5 生成纪要、待办、决议三部分    |
| 5   | 持久化         | 写入 PostgreSQL                    |
| 6   | RAG 索引       | 文本向量化写入 FAISS 知识库         |
| 7   | 文档导出       | 生成 DOCX / MD / PDF              |

### 5.2 页面功能

| 页面   | 功能                                                     |
|-------|---------------------------------------------------------|
| 首页   | 统计概览（会议总数/待办数/平均处理时间）、最近会议卡片、快捷入口 |
| 上传页 | 文件上传（音频/视频）、标题/日期配置、导出格式选择、自定义模板、流式进度展示 |
| 结果页 | 纪要/待办/决议三栏展示、会议概览条（时长/类型/待办数）、原始转录文本（折叠/搜索）、文档下载、底部会议问答 |
| 问答页 | 选择历史会议、多轮对话（含上下文记忆）、RAG 跨会议检索、建议问题 |
| 历史页 | 列表展示、标题搜索、时长/环境筛选、分页、会议删除（含二次确认+向量索引同步删除）|
| 统计页 | 指标卡（总会议/已完成/多人会议/平均处理）、时长分布柱状图、环境分布饼图、月度趋势折线图 |

### 5.3 CLI 命令行功能

```
python main.py transcribe <audio>    # 仅语音识别
python main.py live <audio>          # 实时流式转写
python main.py minutes <audio>       # 生成完整纪要
python main.py export <meeting_id>   # 重新导出文档
python main.py chat <meeting_id>     # 交互式会议问答
python main.py history               # 查看历史会议列表
```

### 5.4 文档导出

- DOCX：纯文本生成 / 自定义模板填充（docxtpl）
- MD：纯文本输出
- PDF：Markdown 转 PDF / 模板填充（PyMuPDF + pypdf）

### 5.5 RAG 知识库

- 基于 FAISS 的向量检索
- 中文友好的递归分隔符分块（chunk_size=512, overlap=64）
- 会议维度隔离（问答时自动排除当前会议，只搜历史会议）
- 低相似度重排序兜底
- 支持会议删除时同步清理向量索引

### 5.6 其他特性

- 文件哈希去重：相同音频重复上传直接命中缓存
- 流式处理模式：边转写边展示，适合长会议
- 自定义模板：支持上传 DOCX/PDF 模板用于导出
- 多轮对话记忆：ChatAgent 内置会话历史管理（最近20轮）
