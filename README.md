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
3. 在 GitHub 发 PR，目标分支选 dev，指定组长 review
4. review 通过后合并，删除 feature 分支

## 项目结构

meeting-agent/
├── modules/        # 核心功能模块（asr, llm, database, exporter）
├── chains/         # LangChain 链
├── rag/            # RAG 知识库（V2.0）
├── templates/      # 文档模板
├── storage/        # 文件存储
├── demo/           # 各成员 Demo
├── app.py          # Streamlit 前端
├── main.py         # 命令行入口
└── requirements.txt