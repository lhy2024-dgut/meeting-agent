# Demo - LHY | AI 会议纪要助手

## 完成的功能

### 核心流程
- 上传本地会议音频（mp3/wav/m4a/flac/ogg），全自动生成结构化会议纪要
- 使用 Whisper ASR 完成语音转文字，无需音频预处理，支持多种格式直接输入
- 使用本地部署的 Qwen2.5 大模型，单次调用同时生成会议纪要、决议事项、待办事项三项内容
- Streamlit 前端，支持文件上传、结果展示、文档下载、对话问答

### 文档导出
- Word (.docx)：基于 docxtpl 模板填充，保留格式和样式
- Markdown (.md)：模板字符串替换输出
- PDF (.pdf)：基于 reportlab 排版引擎，支持中文字体，自动分页

### 数据库
- PostgreSQL 管理会议数据，设计三张表：
  - `meetings`：会议元数据（id、标题、音频路径、创建时间）
  - `transcripts`：转录段落数据（文本、start_time、end_time，支持音频播放同步）
  - `summaries`：纪要内容（summary、decisions、todos，与 meetings 一对一关联）

### LangChain 集成
- `chains/summary_chain.py`：用 LangChain LCEL 构建纪要生成链，`prompt | ChatOllama | JsonOutputParser`
- `chains/chat_chain.py`：带 Memory 的对话链，用 session_state 管理对话历史，最多保留 10 轮

### 对话问答(开发中，待调试)
- 基于本次会议转录内容进行多轮对话追问
- Memory 管理：对话历史转为 HumanMessage/AIMessage 列表，通过 MessagesPlaceholder 注入 Prompt

---

## 技术栈

| 类别 | 技术 |
|---|---|
| 语音识别 | openai-whisper（base 模型，CPU 推理）|
| 大模型推理 | Ollama + Qwen2.5-7B / Qwen2.5-3B |
| LLM 框架 | LangChain（langchain-ollama、langchain-core）|
| 数据库 | PostgreSQL + psycopg2 |
| 文档生成 | docxtpl、python-docx、reportlab |
| 前端 | Streamlit |
| 环境管理 | python-dotenv |

---

## 项目结构

```
meeting_assistant/
├── .env                    # 环境配置（DB密码、模型名称）
├── main.py                 # 命令行入口
├── app.py                  # Streamlit 前端
├── create_templates.py     # 生成初始模板文件
├── requirements.txt
├── modules/
│   ├── asr.py              # Whisper 语音识别
│   ├── llm.py              # 原生 Ollama 调用（备用）
│   ├── database.py         # PostgreSQL 操作
│   └── exporter.py         # 文档导出
├── chains/
│   ├── summary_chain.py    # LangChain 纪要生成链
│   └── chat_chain.py       # LangChain 对话链（含Memory）
├── templates/              # 文档模板
└── storage/
    ├── audio/              # 会议音频存储
    └── output/             # 输出文档存储
```

---

## 现存问题

1. **ASR 速度**：使用原版 Whisper + CPU 推理，6分钟音频处理约需 3 分钟，速度可以继续提升
2. **Word文档输出待优化调试**：输出的word文档中有显示问题，如乱码、格式错乱，需要进一步调试
3. **转录输出繁体字**：Whisper 在部分音频上输出繁体中文，已通过 `initial_prompt` 引导，但是在保存到本地的会议纪要文档中，会议转写仍然是繁体字
4. **无实时转写**：目前只支持录音文件上传，不支持实时麦克风输入

---

## 优化思路

1. **ASR 提速**：换用 `faster-whisper`，底层使用 CTranslate2 + int8 量化，CPU 下速度提升 4~8 倍
2. **模型选型**：对比测试 Qwen2.5-3B vs 7B，会议纪要任务 3B 质量损失有限但速度快一倍
3. **Prompt 优化**：加负面约束（禁止逐条复述）、强制二级标题结构、加 Few-shot 示例
4. **RAG 知识库**：用 ChromaDB 存储历史会议向量，实现跨会议语义检索
5. **实时转写**：用 `sounddevice` 采集麦克风音频，每 3~5 秒切段送 faster-whisper 识别
6. **说话人分离**：引入 `pyannote-audio` 实现多说话人识别