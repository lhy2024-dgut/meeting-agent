# Meeting Agent — AI 会议纪要智能体

## 分支规范

| 分支 | 用途 | 说明 |
|---|---|---|
| main | 生产分支 | 每周末从 dev 合并，需 1人 review |
| dev | 开发集成分支 | 所有 feature 分支合并到这里，需 1人 review |
| feature/xxx | 功能开发分支 | 从 dev 拉出，完成后 PR 到 dev |
| demo/xxx | 个人 Demo | 各自提交到 demo/ 子目录 |

## 开发流程

1. 从 dev 拉出 feature 分支：git checkout -b feature/你的功能名
2. 开发完成后推送：git push origin feature/你的功能名
3. 在 GitHub 发 PR，目标分支选 dev，指定其他人 review
4. review 通过后合并，删除 feature 分支

## 项目结构

```
meeting-agent/
├── app.py                  # Streamlit Web 入口
├── main.py                 # CLI 入口
├── config.py               # 全局配置 + Ollama LLM 封装
├── requirements.txt        # Python 依赖
│
├── agents/                 # 智能体
│   └── chat_agent.py       # 会议问答 Agent（RAG + 多轮对话）
│
├── chains/                 # 处理链
│   ├── minutes_chain.py    # 纪要提取链（ASR 文本 → 待办/决议/纪要）
│   └── export_chain.py     # 文档导出链（DOCX / MD / PDF）
│
├── engines/                # 底层引擎
│   ├── asr_engine.py       # Faster-Whisper 语音识别
│   ├── audio_utils.py      # 音频格式转换 + 视频抽音轨
│   └── pdf_engine.py       # PDF 生成（PyMuPDF + pypdf）
│
├── services/               # 业务编排
│   ├── meeting_service.py  # 7 步会议处理流水线
│   └── file_service.py     # 文件上传 / 哈希 / 存储
│
├── db/                     # 数据库层
│   ├── models.py           # SQLAlchemy ORM（Meeting + Transcription）
│   └── repository.py       # 数据仓储层（CRUD）
│
├── rag/                    # RAG 知识库
│   ├── embeddings.py       # bge-m3 向量嵌入
│   ├── retriever.py        # FAISS 检索器
│   └── text_splitter.py    # 中文文本分块
│
├── prompts/                # Prompt 模板
│   └── templates.py        # 纪要提取 + 会议问答模板
│
├── ui/                     # Streamlit 页面
│   ├── home.py             # 首页（统计 + 最近会议）
│   ├── upload.py           # 上传页（音频/视频 + 参数配置）
│   ├── result.py           # 结果页（纪要/待办/决议/问答）
│   ├── chat.py             # 独立问答页
│   ├── history.py          # 历史会议（搜索/过滤/分页）
│   ├── stats.py            # 数据统计（Plotly 图表）
│   ├── components.py       # 公共 UI 组件
│   └── global_css.py       # 全局样式主题
│
├── storage/                # 本地存储
│   ├── audio/              # 上传的音频文件
│   ├── video/              # 上传的视频文件
│   ├── output/             # 导出的文档
│   ├── templates/          # 自定义导出模板
│   └── vector_store/       # FAISS 向量索引
│
└── demo/                   # 各成员 Demo（不受代码审查）
```