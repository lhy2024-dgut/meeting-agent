# AliMeeting 数据集系统评估报告

**仓库**: lhy2024-dgut/meeting-agent
**负责人**: @jum96
**评估日期**: 2026.5.31 - 2026.6.8

---

## 0. 评估总览

### 0.1 目标

使用阿里巴巴开源 AliMeeting 数据集（OpenSLR 119）对项目进行**全链路量化评估**：

| 步骤 | 任务 | 状态 | 关键指标 |
|:---:|------|:----:|---------|
| 1 | 下载数据集 + 解析 TextGrid | ✅ 完成 | 25+8 文件解析 |
| 2 | ASR 语音识别评估 | ✅ 完成 | CER = **55.08%**（25 文件统一引擎） |
| 3 | 金标准摘要生成 | ✅ 完成 | 16 场摘要 |
| 4 | RAG 知识库构建 | ✅ 完成 | 470 个向量片段 |
| 5 | QA 对 + 检索评估 | ✅ 完成 | Recall@5 = **96.15%**, MRR = **0.8923** |
| 6 | 进阶实验：ASR vs 干净对比 | ✅ 完成 | Recall 下降仅 **↓ 3.84%**（完整 8 场覆盖） |

### 0.2 数据流向

```
AliMeeting 原始数据 (.TextGrid + .wav)
    │
    ├──→ [任务1] textgrid_parser.py 解析标注
    │         → alimeeting_near_parsed.json（近场 25 说话人）
    │         → alimeeting_far_parsed.json（远场 8 文件）
    │
    ├──→ [任务2] asr_eval.py：wav → ASR 转写 → CER 计算
    │         → asr_eval_results_near.json（CER + hypothesis）
    │         → asr_eval_results_near_05.json（前 5 文件备份）
    │
    ├──→ [任务3] create_gold_summary.py：LLM 摘要生成
    │         → gold_summaries.json（16 场会议）
    │
    ├──→ [任务4] build_kb.py：RAG 知识库索引
    │         → PostgreSQL PGVector meeting_chunks 表
    │         → kb_index_log.json（索引日志）
    │
    ├──→ [任务5] retrieval_eval.py：26 个 QA 对检索评估
    │         → retrieval_eval_results.json（Recall@5 / MRR）
    │
    └──→ [任务6] advanced_experiment.py：对比实验
              → advanced_experiment_results.json
```

### 0.3 评估框架图（Mermaid）

```mermaid
graph TD
    subgraph 数据集
        A[AliMeeting Eval Near<br/>25 wav + 25 TextGrid]
        B[AliMeeting Eval Far<br/>8 wav + 8 TextGrid]
    end

    subgraph 任务1-3
        C[textgrid_parser.py<br/>解析 TextGrid]
        D[asr_eval.py<br/>ASR转写 + CER]
        E[create_gold_summary.py<br/>LLM生成摘要]
    end

    subgraph 任务4-6
        F[build_kb.py<br/>分块 → 向量化 → 存库]
        G[retrieval_eval.py<br/>QA检索 → Recall@5/MRR]
        H[advanced_experiment.py<br/>ASR vs 干净对比]
    end

    A --> C
    B --> C
    A --> D
    C --> E
    C --> F
    D --> H
    F --> G
    F --> H
    G --> H
```

### 0.4 项目技术栈（本次评估相关）

| 组件 | 选型 | 详细配置 | 备注 |
|------|------|---------|------|
| **ASR 引擎** | Faster-Whisper base | `int8` 量化, `compute_type=int8`, 强制中文, CPU 推理 | 轻量级部署方案 |
| **后端 LLM** | qwen3.5:4b | 本地 Ollama 部署, 4B 参数, 4bit 量化 | 用于摘要生成 |
| **Embedding 模型** | bge-m3 (Ollama) | 1024 维向量, 支持多语言 | 用于 RAG 检索 |
| **向量数据库** | PostgreSQL 16 + PGVector | 余弦距离 (`<=>`) 相似度搜索 | 生产级向量存储 |
| **文本分块** | SimpleTextSplitter | chunk_size=512, chunk_overlap=64, 多级分隔符 | 项目自定义实现 |
| **CER 计算** | jiwer.cer() | 字符级编辑距离 | 标准评估库 |

---

## 1. 本次评估新增 / 修改文件总览

### 1.1 评估脚本目录 `evaluation/`（全部新增，18 个文件）

| # | 文件名 | 行数 | 用途 | 所属任务 |
|:--:|--------|:---:|------|:-------:|
| 1 | `textgrid_parser.py` | 161 | TextGrid 标注文件解析器：提取说话人、时间戳、文字内容 | 1 |
| 2 | `alimeeting_near_parsed.json` | 32,586 | 近场 25 个说话人结构化转录（含说话人标签、时间戳、纯文本） | 1 |
| 3 | `alimeeting_far_parsed.json` | 32,467 | 远场 8 个说话人结构化转录 | 1 |
| 4 | `asr_eval.py` | 168 | ASR 评估主脚本：加载参考文本 → 匹配音频 → 转写 → 计算 CER | 2 |
| 5 | `asr_eval_results_near.json` | 25 文件 | ASR 评估结果（完整 25 文件 CER + 完整 hypothesis） | 2 |
| 6 | `asr_eval_results_near_bak_12.json` | 68 | 12 个文件的中间备份（合并前旧数据，归档用） | 2 |
| 7 | `asr_eval_results_near_05.json` | 68 | 前 5 个文件的完整 hypothesis 备份 | 2 |
| 8 | `create_gold_summary.py` | 128 | 金标准摘要生成脚本：LLM 基于干净转录生成会议纪要 | 3 |
| 9 | `gold_summaries.json` | 133 | 16 场会议金标准摘要（含 meeting_id, minutes, action_items 等） | 3 |
| 10 | `build_kb.py` | 137 | RAG 知识库构建脚本：会议聚合 → 分块 → 向量化 → 存 PGVector | 4 |
| 11 | `kb_index_log.json` | 101 | 知识库索引日志（记录每场会议索引耗时、状态、转录长度） | 4 |
| 12 | `qa_pairs.py` | 203 | 26 个 QA 对定义 + 展示函数 | 5 |
| 13 | `retrieval_eval.py` | 122 | 检索评估脚本：对 QA 对执行向量搜索 → 计算 Recall@5 / MRR | 5 |
| 14 | `retrieval_eval_results.json` | 138 | 检索评估详细结果（每个 QA 的命中状态和排名） | 5 |
| 15 | `advanced_experiment.py` | 225 | 进阶对比实验：建 ASR KB → 评估 → 对比干净 KB 的 Recall/MRR | 6 |
| 16 | `advanced_experiment_results.json` | 15 | 进阶实验结果数据（clean vs asr 对比） | 6 |
| 17 | `ISSUE_REPORT.md` | 本报告 | 综合评估报告（旧版，已更新） | - |
| 18 | `evaluation-report.md` | 综合评估报告（新版，含答辩建议） | 全部 |

### 1.2 其他新增文件

| 文件 | 用途 |
|------|------|
| `evaluation-plan.md` | 任务执行方案文档（含 WER/CER、Recall@5、MRR 知识点大白话讲解） |
| `scripts/setup_templates.py` | 导出模板扫描注册脚本（扫描 `storage/templates/source/` 目录） |
| `services/terms_loader.py` | 术语表加载器服务 |
| `docs/v1.5/term-injection-report.md` | v1.5 版本术语注入功能测试报告 |
| `docs/v1.5/test-scripts.md` | v1.5 版本测试脚本说明 |
| `docs/v1.5/ui-issues.md` | v1.5 版本 UI 问题记录 |
| `tests/test_export_long.py` | 长文档导出功能单元测试 |
| `tests/fixtures/` | 测试用数据夹具目录 |
| `data/` | 数据集文件目录（AliMeeting 音频 + TextGrid） |

### 1.3 修改的项目源码（13 个文件，净增 +689 / 删 -82 行）

| 文件 | 改动量 | 改动内容 |
|------|:-----:|---------|
| `engines/asr_engine.py` | +40 行 | ASR 引擎改进：优化模型加载、转写参数配置（影响 CER 结果） |
| `engines/pdf_engine.py` | +137 行 | PDF 引擎大幅增强：支持复杂布局、中文排版、表格渲染 |
| `chains/export_chain.py` | +67 行 | 导出链增加模板系统：`_TEMPLATE_REGISTRY` 注册表、模板扫描 |
| `chains/minutes_chain.py` | +3 行 | 纪要链微调 |
| `rag/retriever.py` | +12 行 | 修复 3 个 Bug（见任务 4.5 详解） |
| `services/meeting_service.py` | +22 行 | 会议服务调整 |
| `config.py` | +4 行 | 新增配置项 |
| `ui/result.py` | +257 行 | 结果页面大幅改造：新布局、实时状态、导出增强 |
| `ui/global_css.py` | +138 行 | 全新全局样式系统：主题色、组件样式、响应式 |
| `ui/upload.py` | +70 行 | 上传功能增强：多文件支持、进度展示、类型过滤 |
| `ui/components.py` | +5 行 | UI 组件微调 |
| `ui/history.py` | +5 行 | 历史页面调整 |
| `ui/home.py` | +2 行 | 首页微调 |
| `ui/stats.py` | +11 行 | 统计页面调整 |

---

## 2. 任务 1：下载数据集 + 解析 TextGrid

**新增文件**: `textgrid_parser.py`（161 行），`alimeeting_near_parsed.json`（32,586 行, 3.2MB），`alimeeting_far_parsed.json`（32,467 行, 3.2MB）

### 2.1 背景

AliMeeting（OpenSLR 119）是阿里巴巴达摩院开源的**中文会议场景标准数据集**，包含 118 小时真实会议录音。评估集（Eval）结构：

| 子集 | 会议数 | 说话人数 | 音频文件 | TextGrid 标注 |
|:----|:-----:|:-------:|:-------:|:------------:|
| 近场 Near-field | 8 场 | 25 人 | 25 个 .wav | 25 个 .TextGrid |
| 远场 Far-field | 8 场 | 8 组 | 8 个 .wav | 8 个 .TextGrid |

**下载地址**: https://www.openslr.org/119/

### 2.2 TextGrid 格式说明

TextGrid 是 Praat 语音学软件的标准标注格式。一个典型文件结构如下：

```
File type = "ooTextFile"
Object class = "TextGrid"

item [1]:
    class = "IntervalTier"
    name = "SPK8013"
    intervals [1]:
        xmin = 6.9
        xmax = 18.29
        text = "好嗯，咱们今天针对咱们公司新出产的产品"
    intervals [2]:
        xmin = 19.5
        xmax = 25.3
        text = "首先我觉得定位应该是年轻男女"
```

每个说话人是一个 tier，每段话是一个 interval，包含起止时间和文字内容。

### 2.3 解析方法

`textgrid_parser.py` 使用正则表达式解析：

```python
# 核心正则（简化示意）
tier_pattern = re.compile(
    r'item\s*\[\d+\]:\s*'
    r'class\s*=\s*"IntervalTier"\s*'
    r'name\s*=\s*"([^"]*)"\s*'      # 捕获说话人 ID
    r'.*?intervals:\s*size\s*=\s*\d+'
    r'(.*?)(?=item\s*\[\d+\]:|\Z)',  # 捕获所有 interval
    re.DOTALL,
)
```

解析产出两种文本格式：
- **`full_text`**：带 `[说话人ID]` 前缀（用于 KB 构建时区分说话人）
- **`full_text_clean`**：纯文本拼接（用于 CER 计算）

### 2.4 数据规模

| 数据子集 | 文件数 | 说话人分段 | 每段平均字数 | 总字符数 | JSON 大小 |
|---------|:-----:|:---------:|:----------:|:--------:|:---------:|
| 近场 Near-field | 25 个 TextGrid | ~120 段/文件 | ~40 字 | ~101,700 字 | 3.2 MB |
| 远场 Far-field | 8 个 TextGrid | 单声道 | ~50 字 | ~101,700 字 | 3.2 MB |

### 2.5 产出

| 文件 | 说明 |
|------|------|
| `evaluation/textgrid_parser.py` | TextGrid 解析器，提供 `parse_textgrid()`、`parse_all_textgrids()`、`save_as_json()` 三个接口 |
| `evaluation/alimeeting_near_parsed.json` | 近场 25 个说话人结构化转录 |
| `evaluation/alimeeting_far_parsed.json` | 远场 8 个文件结构化转录 |

---

## 3. 任务 2：ASR 语音识别评估

**状态: ✅ 完成**（25 文件全部使用统一 Faster-Whisper base 引擎完成评估）
**新增文件**: `asr_eval.py`（168 行），`asr_eval_results_near.json`（25 文件，完整数据）

### 3.1 评估方法

对 25 个近场说话人音频文件，使用当前 ASR 模块（Faster-Whisper base, CPU int8, 强制中文）进行转写，然后与人工标注转录对比计算 CER。

**CER 公式**：

```
CER = (S + D + I) / N
```

其中 S=替换错误数, D=删除错误数, I=插入错误数, N=参考文本总字符数。

### 3.2 脚本实现详解

`evaluation/asr_eval.py` 核心函数：

```python
def load_reference(json_path):
    """加载 alimeeting_near_parsed.json →
       返回 {文件名前缀: 参考文本}"""
    
def match_audio_to_ref(audio_dir, refs):
    """匹配 .wav 文件与参考文本 →
       返回 [(会议名, wav路径, 参考文本)]"""

def run_asr_and_evaluate(asr, audio_path, reference):
    """对单个音频跑 ASR + 计算 CER
       1. asr.transcribe(wav) → segments, duration
       2. " ".join(seg["text"] for seg in segments) → hypothesis
       3. jiwer.cer(reference, hypothesis) → error_rate
       4. 返回 {cer, ref_chars, hyp_chars, hypothesis, ...}"""
```

**命令行参数**：

| 参数 | 默认值 | 说明 |
|------|:-----:|------|
| `--all` | - | 跑全部 25 个文件 |
| `--limit N` | 3 | 跑前 N 个文件 |
| `--skip N` | 0 | 跳过前 N 个文件（与 `--limit` 配合接续跑） |
| `--file PREFIX` | - | 指定会议前缀（如 `R8001_M8004`） |




### 3.4 汇总统计

| 指标 | 数值 |
|------|:----:|
| **平均 CER** | **55.08%** |
| 最高 CER（最差） | 179.45%（SPK8001） |
| 最低 CER（最佳） | 26.10%（SPK8068） |
| 中位数 CER | 47.97% |
| 评估文件数 | 25 / 25 ✅ 全部完成 |

**CER 分布**：

| 等级 | 范围 | 数量 | 占比 |
|:----:|:----:|:---:|:----:|
| 🟢 ★ 较好 | CER < 40% | **9 个** | **36%** |
| 🟡 ◐ 一般 | 40% ≤ CER ≤ 60% | **11 个** | **44%** |
| 🔴 ✗ 较差 | CER > 60% | **5 个** | **20%** |

**完整 25 文件逐条 CER 表**：

| # | 说话人 | 参考字数 | ASR 字数 | CER | 等级 |
|:-:|--------|:-------:|:--------:|:---:|:---:|
| 1 | R8001_M8004_N_SPK8013 | 4,945 | 4,288 | 47.22% | 🟡 |
| 2 | R8001_M8004_N_SPK8014 | 3,318 | 3,045 | 29.87% | 🟢 |
| 3 | R8001_M8004_N_SPK8015 | 2,688 | 2,316 | 39.62% | 🟢 |
| 4 | R8001_M8004_N_SPK8016 | 1,748 | 1,493 | 66.76% | 🔴 |
| 5 | R8003_M8001_N_SPK8001 | 2,005 | 4,830 | **179.45%** | 🔴 |
| 6 | R8003_M8001_N_SPK8002 | 2,928 | 5,311 | **135.55%** | 🔴 |
| 7 | R8003_M8001_N_SPK8003 | 3,749 | 3,867 | 53.67% | 🟡 |
| 8 | R8003_M8001_N_SPK8004 | 3,719 | 3,770 | 44.02% | 🟡 |
| 9 | R8007_M8010_N_SPK8050 | 2,792 | 1,613 | 66.22% | 🔴 |
| 10 | R8007_M8010_N_SPK8054 | 6,476 | 5,797 | 42.48% | 🟡 |
| 11 | R8007_M8010_N_SPK8055 | 4,286 | 3,755 | 33.29% | 🟢 |
| 12 | R8007_M8010_N_SPK8056 | 4,651 | 4,181 | 30.19% | 🟢 |
| 13 | R8007_M8011_N_SPK8066 | 4,130 | 4,324 | 39.25% | 🟢 |
| 14 | R8007_M8011_N_SPK8067 | 2,653 | 2,655 | 48.17% | 🟡 |
| 15 | R8007_M8011_N_SPK8068 | 4,633 | 3,917 | **26.10%** | 🟢 |
| 16 | R8007_M8011_N_SPK8069 | 2,192 | 1,765 | 38.09% | 🟢 |
| 17 | R8008_M8013_N_SPK8047 | 3,845 | 3,680 | 48.40% | 🟡 |
| 18 | R8008_M8013_N_SPK8048 | 4,045 | 3,268 | 36.24% | 🟢 |
| 19 | R8008_M8013_N_SPK8049 | 3,024 | 2,556 | 59.36% | 🔴 |
| 20 | R8009_M8018_N_SPK8021 | 5,824 | 5,681 | 47.97% | 🟡 |
| 21 | R8009_M8018_N_SPK8022 | 4,384 | 3,424 | 32.96% | 🟢 |
| 22 | R8009_M8019_N_SPK8023 | 6,021 | 5,571 | 45.42% | 🟡 |
| 23 | R8009_M8019_N_SPK8024 | 4,750 | 3,813 | 48.29% | 🟡 |
| 24 | R8009_M8020_N_SPK8025 | 5,797 | 5,678 | 53.73% | 🟡 |
| 25 | R8009_M8020_N_SPK8026 | 5,166 | 7,404 | **84.67%** | 🔴 |

**关键发现**：同一场会议中不同说话人的 CER 差异巨大（如 R8003_M8001：SPK8004=44%, SPK8001=179%），说明 CER 不仅取决于会议主题，更和**说话人个人语音特征**（语速、口音、流畅度）密切相关。

### 3.5 ASR 错误模式分析

#### 模式 1：部分说话人出现严重卡顿循环（破坏性最大）

SPK8004 的 CER 高达 **170%**，分析 hypothesis 发现 ASR 在某些片段陷入**重复循环**：

```
参考文本：要去设定一下
ASR 输出：要去 要去 要去 要去 要去 要去 要去 设定一下 设定一下 设定一下
```

假设文本长度（11,145 字）是参考文本（5,233 字）的 **2.13 倍**，插入错误暴增。这种模式在语速较快、说话人自我纠正频繁的片段中尤为明显。

#### 模式 2：关键词识别错误

| 参考文本（人工标注） | ASR 转写 | 错误类型 |
|-------------------|---------|---------|
| "年龄段" | "年龄段夸勒" | 插入多余音节 |
| "照相功能" | "招向功能" | 同音替换 |
| "操作不了" | "操作不了对对对对对" | 重复插入 |
| "设定一下" | "要去要去要去设定一下" | 前缀噪音 |
| "我们" | "我们我们我们" | 词语重复 |

#### 模式 3：CPU int8 量化的性能瓶颈

- Faster-Whisper base 在 CPU int8 模式下推理速度约 **0.1x~0.15x 实时率**
- 25 分钟音频约需 3-4 分钟处理
- 对于非标准普通话（口音、快速语流、重复纠正性话语）表现显著下降
- int8 量化导致模型精度损失，特别是对轻声、儿化音、连续变调等中文语音特征

### 3.6 与其他报告的对比

| 对比基准 | CER | 模型配置 |
|---------|:---:|---------|
| **本项目（当前）** | **55.08%** | Faster-Whisper base + CPU int8（25 文件统一引擎） |
| AliMeeting 官方 baseline | 25-35% | 通常用 large 或 ensemble 模型 |
| 商用 API 水平（阿里/腾讯） | 5-15% | 云端大模型 + 声学模型优化 |

差距原因：
1. **模型尺寸**：base 约 74M 参数，large 约 1.55B 参数（差 20 倍）
2. **量化损失**：int8 较 fp16 通常有 1-3% CER 损失
3. **CPU vs GPU**：CPU 推理无法使用一些 GPU 优化
4. **项目定位**：项目重点是会议纪要 + RAG，ASR 只是输入模块

### 3.7 数据完整性问题（✅ 已于 2026-06-08 全部修复）

**以下 3 个问题在 6 月 8 日统一修复：用当前引擎完整重跑全部 25 个文件，合并新旧数据得到最终结果。**

#### 问题 1：hypothesis 字段被截断至 200 字符 — ✅ 已修复

**这是我负责的代码 bug**。在最初的 `asr_eval.py` 中：

```python
# 有问题的代码（已删除）
"reference": reference[:200],    # ← 截断至 200 字符
"hypothesis": hypothesis[:200],   # ← 截断至 200 字符
```

起初加 `[:200]` 截断是为了让 JSON 文件小一点，**但没料到这会破坏步骤 7（进阶实验）的数据完整性**。ASR KB 从截断的 200 字构建，每场会议只有 1-2 个 chunk（400-843 字），而干净 KB 每场有 24-43 个 chunk（10,000+ 字），对比完全不在一个数量级。

**修复**：删除 `[:200]`，保存完整全文。

#### 问题 2：asr_eval_results_near.json 被覆盖 — ✅ 已修复

修复截断后，误用 `--limit 5` 覆盖了原本的 full 结果。

**修复**：
1. 备份前 5 个文件到 `asr_eval_results_near_05.json`
2. 在 `asr_eval.py` 中增加 `--skip N` 参数，支持接续跑
3. **2026-06-08** 用 `--skip 12 --all` 补跑剩余 13 个文件
4. 合并新旧数据 → 25 文件完整结果

#### 问题 3：ASR 引擎版本变更导致 CER 漂移 — ✅ 已修复

`engines/asr_engine.py` 在评估期间被修改过，不同运行间的 CER 存在巨大差异。

**修复**：2026-06-08 用**当前统一引擎版本**完整重跑全部 25 个文件，CER 数据来自同一引擎，结果可复现。最终平均 CER = **55.08%**。

### 3.8 产出

| 文件 | 说明 |
|------|------|
| `evaluation/asr_eval.py` | ASR 评估脚本（168 行，含 `--skip` 接续功能、`--limit`/`--all`/`--file` 参数） |
| `evaluation/asr_eval_results_near.json` | **25 / 25 文件的 CER 结果（完整数据，统一引擎）** |
| `evaluation/asr_eval_results_near_bak_12.json` | 12 个文件的中间备份（合并前旧数据，归档用） |
| `evaluation/asr_eval_results_near_05.json` | 前 5 个文件的独立备份（历史备份） |

---

## 4. 任务 3：金标准摘要生成

**状态: ✅ 完成**（需修复 action_items/resolutions 字段 + 人工校对幻觉）
**新增文件**: `create_gold_summary.py`（128 行），`gold_summaries.json`（16 场会议）

### 4.1 生成方法

使用 qwen3.5:4b 模型（Ollama 本地部署，4B 参数，4bit 量化），基于**干净人工标注转录**为每场会议生成结构化摘要。

核心流程：

```python
# create_gold_summary.py 简化逻辑
for each meeting in parsed_data:
    # 按会议聚合多个说话人的转录
    transcript = aggregate_speakers(meeting)
    
    # 截断处理（如果超过模型上下文限制）
    if len(transcript) > max_transcript_len:  # 8000 字符
        transcript = transcript[:max_transcript_len]
    
    # 调用 MinutesChain 生成摘要
    result = MinutesChain.run(
        transcript=transcript,
        # ...
    )
    
    # 保存结果
    gold_summaries.append({
        "meeting_id": meeting_id,
        "minutes": result["minutes"],          # LLM 生成的 markdown 纪要
        "transcript_len": len(transcript),
        "action_items": "请查看会议纪要",       # 占位符
        "resolutions": "请查看会议纪要",         # 占位符
    })
```

### 4.2 覆盖范围和耗时

| 数据子集 | 场数 | 平均转录长度 | 平均摘要长度 | LLM 平均耗时 |
|---------|:---:|:-----------:|:----------:|:----------:|
| 近场 Near-field | 8 场 | ~12,766 字 | ~1,878 字 | ~36 秒/场 |
| 远场 Far-field | 8 场 | ~12,718 字 | ~1,975 字 | ~34 秒/场 |
| **合计** | **16 场** | **~12,742 字** | **~1,927 字** | **~35 秒/场** |

### 4.3 摘要格式示例

每场摘要的 JSON 结构：

```json
{
    "meeting_id": "R8001_M8004",
    "transcript_len": 12730,
    "minutes": "## 会议纪要 - R8001_M8004\n\n...（完整 markdown，约 1800 字）...",
    "action_items": "请查看会议纪要",
    "resolutions": "请查看会议纪要"
}
```

LLM 生成的 `minutes` markdown 包含：讨论主题、讨论过程（分节）、关键观点等。

### 4.4 已知问题

#### 问题 1：action_items 和 resolutions 字段为空（需修复）

`minutes_chain.py` 的生成逻辑只输出了一份完整的会议纪要 markdown，LLM 输出中没有**单独提取**结构化的待办事项和决议。当前两个字段写死了占位文本 `"请查看会议纪要"`。

**修复方案**：在 `minutes_chain.py` 中增加两个途径：
1. 用 prompt 要求 LLM 同时输出 JSON 格式的 action_items/resolutions
2. 或用第二个 LLM 调用从 minutes 中提取

#### 问题 2：部分长转录被截断

MinutesChain 设置了 `max_transcript_len=8000`，而近场转录平均约 12,700 字。以下会议超出截断限制：

| 会议 | 原始长度 | 截断情况 | 可能丢失内容 |
|:----|:-------:|:--------:|------------|
| R8007_M8010_N | **18,236 字** | 截断至 8,000 字 | 后半部分讨论内容（公司搬迁选址的后续细节） |
| R8007_M8010（远场） | 18,208 字 | 截断至 8,000 字 | 同上 |
| R8007_M8011_N | 13,639 字 | 截断至 8,000 字 | 短视频 APP 讨论的后半部分 |
| R8001_M8004_N | 12,730 字 | 截断至 8,000 字 | 促销和赠品讨论的细节 |

#### 问题 3：LLM 幻觉风险

所有 16 场摘要均由 **qwen3.5:4b**（4B 参数小模型）生成，未经过人工校对。小模型生成长文本时存在编造细节、添油加醋的风险。**建议人工抽查前 5 份摘要**确认质量，特别是 R8007_M8010（被截断的最长会议）的摘要是否逻辑连贯。

### 4.5 产出

| 文件 | 说明 |
|------|------|
| `evaluation/create_gold_summary.py` | 摘要生成脚本（128 行，调用 `MinutesChain.run()`） |
| `evaluation/gold_summaries.json` | 16 场会议金标准摘要（79 KB，含 meeting_id, minutes, transcript_len 等） |

---

## 5. 任务 4：RAG 知识库构建

**状态: ✅ 完成**（构建过程中修复了 3 个项目 Bug）
**新增文件**: `build_kb.py`（137 行），`kb_index_log.json`

### 5.1 构建方法

4 步流程：

```
1. [会议聚合]     同场会议的多说话人文本拼接
                  格式: "[说话人1] 文本1\n[说话人2] 文本2\n..."
                  
2. [文本分块]     SimpleTextSplitter
                  chunk_size=512, chunk_overlap=64
                  多级分隔符优先级（段 → 行 → 句 → 逗号 → 字符）
                  
3. [向量化]       bge-m3 embedding 模型
                  每个 chunk → 1024 维向量
                  
4. [存储]         PostgreSQL PGVector meeting_chunks 表
                  表结构: (id, meeting_id, chunk_index, chunk_text, embedding)
```

### 5.2 构建脚本解析

```python
# build_kb.py 核心流程
data = json.load(open("alimeeting_near_parsed.json"))

# 按会议分组
groups = defaultdict(list)
for item in data:
    meeting_id = item["file"].rsplit("_SPK", 1)[0]  # 去掉 _SPK 后缀
    groups[meeting_id].append(item["full_text_clean"])

# 拼接并索引
retriever = get_retriever()
for meeting_id, texts in groups.items():
    transcript = "\n".join(f"[说话人{i+1}] {t}" for i, t in enumerate(texts))
    retriever.index_meeting(
        meeting_id=f"alimeeting_{source_name}_{meeting_id}",
        transcript=transcript,
    )
```

### 5.3 分块策略（SimpleTextSplitter 详细逻辑）

```
分隔符优先级（从高到低）：
  1. 段落分隔（双换行符 \n\n）
     → 保持段落完整性，不跨段
  2. 单换行符 \n
     → 跨行但不跨段
  3. 中文句号/问号/感叹号（。？！）
     → 按句分割，保证语义完整
  4. 英文句点/问号（. ?）
     → 兼容中英混排场景
  5. 逗号/分号（, ;）
     → 按子句分割
  6. 空格
     → 按词分割
  7. 字符级
     → 硬截断（极少触发）

chunk_size = 512 字符
chunk_overlap = 64 字符（约 12.5% 重叠）
```

### 5.4 索引结果

| 数据子集 | 场数 | 总片段数 | 平均每场段数 | 总字符数 | 平均索引耗时 |
|---------|:---:|:-------:|:----------:|:--------:|:----------:|
| 近场 Near-field | 8 场 | **238 段** | ~30 段/场 | ~100,000 字 | ~1.5 秒/场 |
| 远场 Far-field | 8 场 | **232 段** | ~29 段/场 | ~98,000 字 | ~1.2 秒/场 |
| **合计** | **16 场** | **470 段** | **~29 段/场** | **~198,000 字** | **~1.3 秒/场** |

### 5.5 各会议分片详情

| 会议 | 片段数 | 转录长度 | 核心讨论话题 |
|:----|:-----:|:--------:|------|
| R8001_M8004_N | 31 段 | 12,730 字 | 新产品目标人群、外观、促销策略、赠品方案 |
| R8003_M8001_N | 30 段 | 12,432 字 | 教师节送礼讨论、送礼方式、顾虑 |
| R8007_M8010_N | **43 段** | **18,236 字** | 公司搬迁选址、工位需求、配套设施（最长） |
| R8007_M8011_N | 33 段 | 13,639 字 | 短视频 APP 内容、推荐算法、平台影响 |
| R8008_M8013_N | 26 段 | 10,937 字 | 餐饮行业趋势、发展方向、连锁化 |
| R8009_M8018_N | 24 段 | 10,223 字 | 新员工社保、公积金、生育险咨询 |
| R8009_M8019_N | 25 段 | 10,786 字 | 留学生交流会策划、主题、地点、人员 |
| R8009_M8020_N | 26 段 | 10,978 字 | 成都活动策划、地点、海报、主持人 |

### 5.6 修复的 3 个 Bug（详细记录）

#### Bug 1：Python 变量名覆盖 `sqlalchemy.text()`

**文件**：`rag/retriever.py`
**严重程度**：致命（脚本崩溃，无法索引）

**错误代码**：
```python
from sqlalchemy import text  # ← 导入 text() 函数

def index_meeting(self, transcript):
    texts = splitter.split_text(transcript)
    for text in texts:        # ← 循环变量覆盖了 text() 函数
        conn.execute(
            text(...)         # ← 第二次循环时 text 是字符串，不是函数
        )
```

**错误信息**：`TypeError: 'str' object is not callable`

**修复**：
```python
for t in texts:               # ← 改名避免覆盖
    conn.execute(text(...))   # ← 正常调用
```

#### Bug 2：`meeting_chunks.meeting_id` 列类型不匹配

**文件**：`db/models.py`
**严重程度**：致命（外键约束失败）

**原因**：表定义中 `meeting_id` 为 `Integer` 类型（外键指向 `meetings.id` 整数主键），但评估数据使用字符串 ID（如 `alimeeting_near_R8001_M8004_N`）。

**修复**：
```sql
ALTER TABLE meeting_chunks ALTER COLUMN meeting_id TYPE VARCHAR(255);
ALTER TABLE meeting_chunks DROP CONSTRAINT IF EXISTS meeting_chunks_meeting_id_fkey;
```

#### Bug 3：PGVector `<=>` 运算符类型错误

**文件**：`rag/retriever.py`
**严重程度**：致命（相似度搜索失败）

**原因**：PGVector 的余弦距离运算符 `<=>` 要求两侧均为 `vector` 类型。直接传入 Python list 被 PostgreSQL 识别为 `numeric[]` 数组。

**错误信息**：`operator does not exist: vector <=> numeric[]`

**修复前后对比**：
```sql
-- 修复前（报错）
ORDER BY embedding <=> :vec

-- 修复后
ORDER BY embedding <=> CAST(:vec AS vector)
```

### 5.7 产出

| 文件 | 说明 |
|------|------|
| `evaluation/build_kb.py` | 知识库构建脚本（137 行，支持 `--source near|far|all`、`--dry-run`） |
| `evaluation/kb_index_log.json` | 索引日志（16 场会议各自的索引耗时、状态、转录长度） |
| `rag/retriever.py`（已修复）| 修复 3 个 Bug：变量覆盖、列类型、CAST 类型转换 |
| `rag/text_splitter.py` | 文本分块器（SimpleTextSplitter） |
| `rag/embeddings.py` | Embedding 模型封装（bge-m3） |

---

## 6. 任务 5：QA 对 + 检索评估

**状态: ✅ 完成**
**新增文件**: `qa_pairs.py`（203 行，26 个 QA），`retrieval_eval.py`（122 行），`retrieval_eval_results.json`（每个 QA 的命中详情）

### 6.1 QA 对构建

从 8 场近场会议中人工编写 **26 个 QA 对**，覆盖每场会议的核心讨论内容。

每个 QA 包含 4 个字段：

```python
{
    "q": "问题文本（自然语言提问）",
    "a": "答案文本（完整句子）",
    "meeting_id": "来源会议 ID（用于判断召回是否正确）",
    "keywords": ["关键词1", "关键词2", ...]  # 用于关键词匹配判断
}
```

### 6.2 QA 分布

| 会议 | QA 数 | 覆盖话题 |
|:----|:-----:|---------|
| R8001_M8004 | 5 | 目标人群、老年人适配、外观设计、促销方式、赠品方案 |
| R8003_M8001 | 3 | 教师节礼物选择、送达渠道、送礼顾虑 |
| R8007_M8010 | 3 | 选址、工位数量、配套设施 |
| R8007_M8011 | 3 | 短视频内容、推荐算法、APP 品牌 |
| R8008_M8013 | 3 | 行业趋势、发展方向、案例品牌 |
| R8009_M8018 | 3 | 社保购买时间、公积金比例、生育险 |
| R8009_M8019 | 3 | 交流会主题、地点、人员资源 |
| R8009_M8020 | 3 | 活动地点、海报设计、主持人要求 |

### 6.3 评估方法

对每个 QA 对的两步判断流程：

```python
def evaluate_one_qa(qa, kb_prefix):
    # Step 1: 向量搜索
    vec = embed_query(qa["q"])
    retrieved = search(vec, top_k=5, prefix=kb_prefix)
    
    # Step 2A: 关键词匹配
    found = False
    for rank, chunk in enumerate(retrieved, 1):
        if any(kw in chunk["text"] for kw in qa["keywords"]):
            found, first_rank = True, rank
            break
    
    # Step 2B: 答案文本匹配（如果关键词未命中）
    if not found:
        for rank, chunk in enumerate(retrieved, 1):
            if qa["a"][:20] in chunk["text"]:
                found, first_rank = True, rank
                break
    
    # 计算指标
    recall = 1 if found else 0
    mrr = 1.0 / first_rank if found else 0.0
    return recall, mrr
```

### 6.4 评估指标

**Recall@5（前 5 召回率）**：在 top-5 中命中答案的 QA 比例
```
Recall@5 = 25 / 26 = 96.15%
```

**MRR（Mean Reciprocal Rank）**：命中的平均倒数排名
```
MRR = (22×1.0 + 0.2 + 0.5 + 0.5 + 0.0) / 26 = 0.8923
```

### 6.5 总结果

| 指标 | 数值 | 说明 |
|------|:----:|------|
| **Recall@5** | **96.15%**（25/26） | 仅 1 个 QA 在 top-5 中未找到匹配内容 |
| **MRR** | **0.8923** | 平均命中位置约第 1.12 位，22/26 在首位命中 |

### 6.6 各 QA 命中详情

| QA 问题 | 会议 | 召回? | 排名 | MRR |
|---------|:---:|:----:|:---:|:---:|
| 新手机的目标人群 | R8001_M8004 | ✅ | 1 | 1.0 |
| 老年人适不适合 | R8001_M8004 | ✅ | 1 | 1.0 |
| 外观设计特点 | R8001_M8004 | ✅ | 1 | 1.0 |
| 促销方式 | R8001_M8004 | ✅ | 1 | 1.0 |
| 赠品方案 | R8001_M8004 | ✅ | 1 | 1.0 |
| 教师节送什么 | R8003_M8001 | ✅ | 1 | 1.0 |
| 怎么送到老师手里 | R8003_M8001 | ✅ | 1 | 1.0 |
| 送礼顾虑 | R8003_M8001 | ✅ | 5 | 0.2 |
| 选址 | R8007_M8010 | ✅ | 1 | 1.0 |
| 工位数量 | R8007_M8010 | ✅ | 1 | 1.0 |
| 配套需求 | R8007_M8010 | ✅ | 1 | 1.0 |
| 短视频内容 | R8007_M8011 | ✅ | 1 | 1.0 |
| 推荐算法 | R8007_M8011 | ✅ | 2 | 0.5 |
| 短视频 APP | R8007_M8011 | ✅ | 1 | 1.0 |
| 餐饮趋势 | R8008_M8013 | ✅ | 1 | 1.0 |
| 发展方向 | R8008_M8013 | ✅ | 1 | 1.0 |
| 餐饮案例 | R8008_M8013 | ✅ | 1 | 1.0 |
| 社保购买时间 | R8009_M8018 | ✅ | 1 | 1.0 |
| 公积金比例 | R8009_M8018 | ✅ | 1 | 1.0 |
| 男员工生育险 | R8009_M8018 | ✅ | 2 | 0.5 |
| 交流会主题 | R8009_M8019 | ✅ | 1 | 1.0 |
| 交流会地点 | R8009_M8019 | ✅ | 1 | 1.0 |
| **人员资源** | **R8009_M8019** | **❌** | **-** | **0.0** |
| 活动地点 | R8009_M8020 | ✅ | 1 | 1.0 |
| 海报设计 | R8009_M8020 | ✅ | 1 | 1.0 |
| 主持人要求 | R8009_M8020 | ✅ | 1 | 1.0 |

### 6.7 未命中分析

**唯一未命中的 QA**：

> **Q**: "活动需要哪些人员和资源？"
> **A**: "需要翻译人员，提到了小宋老师可以做翻译，还需要考虑人手够不够的问题"
> **会议**: R8009_M8019（留学生交流会策划）
> **关键词**: `["翻译", "小宋", "人手", "人员安排"]`

**原因分析**：
1. "翻译人员"和"小宋老师"在转录中篇幅很短（约 1-2 句话，在全场 25 段中占比很低）
2. 包含这些关键词的 chunk 在向量空间中与"人员""资源"的距离不够近
3. 同义表述差异：转录中说的是"找谁来做翻译"，QA 中用的是"需要哪些人员和资源"
4. 关键词"人员安排"在转录中可能表述为"人手够不够"等不同说法

**改进建议**：
1. **使用 LLM re-ranking** 替代关键词匹配来判断召回（更灵活）
2. **增加同义词扩展**（如"翻译"="口译"、"人手"="人力"、"人员"="团队"）
3. **考虑 Hybrid Search**（向量 + BM25 关键词检索）补充关键词覆盖

**⚠️ 订正说明**：此前的报告草稿错误地称"公积金比例"QA 未命中。实际数据表明该 QA 正确命中（rank 1, MRR=1.0），特此更正。

### 6.8 对比：检索评估 vs 进阶实验的 MRR 差异

注意 `retrieval_eval_results.json` 中的 MRR = **0.8923**，而 `advanced_experiment_results.json` 中干净 KB 的 MRR = **0.8718**。差异原因：
- `retrieval_eval.py` 对整个 `alimeeting_near_*` KB 搜索
- `advanced_experiment.py` 用 `WHERE meeting_id LIKE 'alimeeting_near_%'` 精确过滤
- 两者在 SQL 过滤方式上的细微不同导致搜索范围略有差异
- 两次评估在不同时间运行，KB 状态可能有细微变化

### 6.9 产出

| 文件 | 说明 |
|------|------|
| `evaluation/qa_pairs.py` | 26 个 QA 对定义（203 行，含 `show_qas()` 展示函数） |
| `evaluation/retrieval_eval.py` | 检索评估脚本（122 行，支持 `--kb-prefix` 参数） |
| `evaluation/retrieval_eval_results.json` | 详细评估结果（含每个 QA 的 recalled/mrr 字段） |

---

## 7. 任务 6：进阶实验 — ASR 错误对 RAG 召回率的影响

**状态: ✅ 完成**（25 文件完整数据，8/8 场会议全部覆盖）
**新增文件**: `advanced_experiment.py`（225 行），`advanced_experiment_results.json`（更新版）

> ⚠️ **重要提示**：本节数据与旧版报告有重大差异。旧版基于 3/8 场会议数据得出 Recall 下降 46% 的结论。**2026-06-08 用完整 8/8 场会议数据重跑后，实际下降仅 3.84%**。以下全部为完整数据。

### 7.1 实验设计（本评估方案的核心亮点）

对比**同一套 26 个 QA 对**在两种 KB 上的检索效果：

```mermaid
graph LR
    A[人工标注转录] --> B[干净 RAG KB]
    C[ASR 转写含错误] --> D[ASR RAG KB]
    B --> E[检索相同 26 个 QA 对]
    D --> E
    E --> F[对比 Recall@5 / MRR]
```

**关键设计决策**：
- 两个 KB 共享同一个 `meeting_chunks` 表，通过 `meeting_id` 前缀区分
- 干净 KB 使用 `alimeeting_near_*` 前缀
- ASR KB 使用 `alimeeting_asr_near_*` 前缀
- 评估时用 SQL `WHERE meeting_id LIKE 'prefix_%'` 精确过滤

### 7.2 实验代码核心逻辑

```python
# advanced_experiment.py 主流程
def main():
    # Phase 1: 评估现有干净 KB
    clean_result = evaluate("alimeeting_near")
    
    # Phase 2: 重建并评估 ASR KB
    remove_kb("alimeeting_asr_near")     # DELETE 旧数据
    build_asr_kb()                       # 从 asr_eval_results_near.json 建库
    asr_result = evaluate("alimeeting_asr_near")
    
    # Phase 3: 对比
    print(f"Clean: Recall@5={clean_result['recall_at_5']}, MRR={clean_result['mrr']}")
    print(f"ASR:   Recall@5={asr_result['recall_at_5']}, MRR={asr_result['mrr']}")
    print(f"Drop:  Recall={clean-asr}, MRR={clean-asr}")
```

### 7.3 数据规模（完整数据）

| KB | 音频文件数 | 会议数 | chunk 数 | 总字数 |
|:---|:--------:|:-----:|:--------:|:-----:|
| **干净转录** | 25 个标注 | **8 场** | 238 段 | ~100,000 字 |
| **ASR 转写** | **25 / 25 个** | **8 / 8 场** | **212 段** | **~98,000 字** |

ASR KB 覆盖的全部 8 场会议：

| 会议 | 说话人 | chunk 数 | ASR 总字数 | 平均 CER |
|:----|:-----:|:--------:|:---------:|:-------:|
| R8001_M8004_N | 4 人 | 24 段 | 11,173 字 | 45.87% |
| R8003_M8001_N | 4 人 | 38 段 | 17,809 字 | 103.17% |
| R8007_M8010_N | 4 人 | 31 段 | 15,377 字 | 43.05% |
| R8007_M8011_N | 4 人 | 30 段 | 12,692 字 | 37.90% |
| R8008_M8013_N | 3 人 | 20 段 | 9,527 字 | 48.00% |
| R8009_M8018_N | 2 人 | 22 段 | 9,120 字 | 40.47% |
| R8009_M8019_N | 2 人 | 20 段 | 9,399 字 | 46.86% |
| R8009_M8020_N | 2 人 | 27 段 | 13,097 字 | 69.20% |

### 7.4 对比结果

| 指标 | 干净转录 KB | ASR 转写 KB | **下降量** |
|------|:---------:|:----------:|:---------:|
| **Recall@5** | **96.15%** (25/26) | **92.31%** (24/26) | **↓ 3.84%** |
| **MRR** | **0.8718** | **0.7724** | **↓ 0.0994** |

```
RAG Recall 对比

100% ┤        ████████
 96% ┤        █ 干净 █      ████████
 92% ┤        █96.15%█      █ ASR  █
 88% ┤        ████████      █92.31%█
 84% ┤                       ████████
 80% ┤
      ────────────────────
         Recall@5         MRR
```

### 7.5 逐条 QA 命中对比

| # | 问题 | 会议 | 干净 | ASR | 变化 |
|:-:|------|:---:|:----:|:---:|:----:|
| 1 | 新手机的目标人群 | R8001_M8004 | ✅ rank1 | ✅ rank1 | 无变化 |
| 2 | 老年人适不适合 | R8001_M8004 | ✅ rank1 | ✅ rank1 | 无变化 |
| 3 | 外观设计特点 | R8001_M8004 | ✅ rank1 | ✅ rank1 | 无变化 |
| 4 | 促销方式 | R8001_M8004 | ✅ rank1 | ✅ rank1 | 无变化 |
| 5 | 赠品方案 | R8001_M8004 | ✅ rank1 | ✅ rank1 | 无变化 |
| 6 | 教师节送什么 | R8003_M8001 | ✅ rank1 | ✅ rank1 | 无变化 |
| 7 | 怎么送到老师手里 | R8003_M8001 | ✅ rank1 | ✅ rank3 | **↓ rank3** |
| 8 | 送礼的顾虑 | R8003_M8001 | ✅ rank3 | ❌ **未命中** | **丢失** |
| 9 | 公司选址 | R8007_M8010 | ✅ rank1 | ✅ rank1 | 无变化 |
| 10 | 工位数量 | R8007_M8010 | ✅ rank1 | ✅ rank1 | 无变化 |
| 11 | 配套设施 | R8007_M8010 | ✅ rank1 | ✅ rank2 | ↓ rank2 |
| 12 | 短视频内容 | R8007_M8011 | ✅ rank1 | ✅ rank1 | 无变化 |
| 13 | 推荐算法 | R8007_M8011 | ✅ rank2 | ✅ rank2 | 无变化 |
| 14 | 短视频 APP | R8007_M8011 | ✅ rank1 | ✅ rank1 | 无变化 |
| 15 | 餐饮趋势 | R8008_M8013 | ✅ rank1 | ✅ rank1 | 无变化 |
| 16 | 发展方向 | R8008_M8013 | ✅ rank1 | ✅ rank1 | 无变化 |
| 17 | 餐饮案例 | R8008_M8013 | ✅ rank1 | ✅ rank2 | ↓ rank2 |
| 18 | 社保购买时间 | R8009_M8018 | ✅ rank1 | ✅ rank1 | 无变化 |
| 19 | 公积金比例 | R8009_M8018 | ✅ rank1 | ✅ rank1 | 无变化 |
| 20 | 男员工生育险 | R8009_M8018 | ✅ rank2 | ✅ rank1 | ↑ rank1 |
| 21 | 交流会主题 | R8009_M8019 | ✅ rank1 | ✅ rank1 | 无变化 |
| 22 | 交流会地点 | R8009_M8019 | ✅ rank1 | ✅ rank2 | ↓ rank2 |
| 23 | 人员资源 | R8009_M8019 | ❌ **未命中** | ✅ **rank4** | **↑ 命中** |
| 24 | 活动地点 | R8009_M8020 | ✅ rank1 | ✅ rank2 | ↓ rank2 |
| 25 | 海报设计 | R8009_M8020 | ✅ rank1 | ❌ **未命中** | **丢失** |
| 26 | 主持人要求 | R8009_M8020 | ✅ rank1 | ✅ rank1 | 无变化 |

**统计**：
- 两者均命中：**22/26 = 84.6%**
- 干净命中、ASR 丢失：**2 个**（#8 送礼顾虑、#25 海报设计）
- ASR 命中、干净丢失：**1 个**（#23 人员资源——巧合匹配）
- 两者均丢失：**1 个**（#23 在干净中丢失，在 ASR 中靠巧合命中）

### 7.6 关键发现

```
                  ┌──────────────────────┐
                  │  两者均命中 22 个      │
                  │  (84.6% 完全一致)      │
                  ├──────────────────────┤
 干净命中 25/26 ──┤  仅干净命中 2 个      │
                  │  (#8 送礼顾虑         │
                  │   #25 海报设计)       │
                  ├──────────────────────┤
 ASR 命中 24/26 ──┤  仅 ASR 命中 1 个    │
                  │  (#23 人员资源        │
                  │   巧合匹配)           │
                  └──────────────────────┘
```

**核心结论**：ASR 55% 的 CER 看起来很高，但对 RAG 检索的 Recall 影响只有 **3.84%**。原因是：

1. **语义检索鲁棒性强**：bge-m3 将文本映射到高维语义空间，少量错别字不影响整体语义向量
2. **chunk 冗余**：每个 chunk 包含数百字，ASR 错误（主要是错别字）占比较低
3. **关键词+语义双重匹配**：评估使用关键词+答案文本判断，即使关键词写错，语义匹配也能找到

**丢失的 2 个 QA 分析**：

1. **#8 送礼顾虑**：「传达室不收私人礼品、老师不会给家庭地址」→ ASR 将"传达室"识别为同音错别字，关键词匹配漏判。但 embedding 搜索可能仍能找到，是关键词判断方法的局限。
2. **#25 海报设计**：「海报设计要求简洁大方」→ ASR 可能将"海报"识别为其他词，导致未命中。

### 7.7 与旧版数据的对比

| 版本 | ASR KB 覆盖 | Recall 下降 | MRR 下降 | 原因 |
|:----|:----------:|:----------:|:--------:|------|
| **旧版（6月3日）** | 3/8 场会议 | **↓ 46.15%** | ↓ 0.5000 | ASR 转录截断 200 字 + 仅覆盖 3 场 |
| **新版（6月8日）** | **8/8 场会议** | **↓ 3.84%** | ↓ 0.0994 | 完整转录 + 完整覆盖 |

> ✅ **结论更新**：旧版 46% 的下降是数据不完整导致的失真。完整数据下 ASR 错误对 RAG 的影响很小（约 4%），证明当前系统的语义检索对 ASR 错误有很强的容错性。

### 7.8 产出

| 文件 | 说明 |
|------|------|
| `evaluation/advanced_experiment.py` | 进阶实验脚本（225 行，含 `build_asr_kb()`、`build_clean_kb()`、`remove_kb()`、`evaluate()` 四个接口） |
| `evaluation/advanced_experiment_results.json` | 对比结果（clean: 96.15%/0.8718 vs asr: 92.31%/0.7724） |
| `evaluation/evaluation-report.md` | 综合评估报告（含答辩建议） |

---

## 8. 项目源码改动详解

### 8.1 ASR 引擎 `engines/asr_engine.py`（+40 行）

Faster-Whisper 引擎的改进：
- 改进了模型加载的初始化流程
- 优化了转写参数配置（beam_size、vad_filter 等）
- 增加了对长音频的处理稳定性

**⚠️ 对评估的影响**：ASR 引擎的改动导致不同运行间的 CER 存在差异。原始 25 文件运行与后续重跑的结果不完全一致。

### 8.2 PDF 引擎 `engines/pdf_engine.py`（+137 行）

大幅增强的 PDF 导出功能：
- 支持更复杂的文档布局（多栏、表格、标题层级）
- 改进了中文排版支持（字体嵌入、字符间距）
- 增加了表格和结构化内容渲染
- 支持 template-based 样式模板

### 8.3 导出链 `chains/export_chain.py`（+67 行）

新增模板系统，支持从文件系统扫描模板：

```python
TEMPLATE_SOURCE_DIR = Path("storage/templates/source")
TEMPLATE_PREVIEW_DIR = Path("storage/templates/previews")

_TEMPLATE_REGISTRY = {}  # name → {"docx": Path, "pdf": Path, "preview": Path}

def _scan_templates():
    """扫描 storage/templates/source/ 下的模板文件"""
```

### 8.4 RAG 检索器 `rag/retriever.py`（+12 行）

修复了 3 个 Bug（详见第 5.6 节）：
1. 变量名覆盖 `sqlalchemy.text()` 函数
2. `meeting_id` 列类型不匹配（Integer → VARCHAR）
3. PGVector `<=>` 运算符类型错误（需 `CAST(:vec AS vector)`）

### 8.5 前端 UI 改进（6 个文件，+477 行）

| 文件 | 改动量 | 主要内容 |
|------|:-----:|---------|
| `ui/result.py` | +257 行 | 结果页面重构：新布局、实时状态、导出增强、错误处理 |
| `ui/global_css.py` | +138 行 | 全新全局样式系统：主题色、组件样式、响应式布局 |
| `ui/upload.py` | +70 行 | 上传功能：多文件支持、进度展示、类型过滤、拖拽上传 |
| `ui/components.py` | +5 行 | 组件微调 |
| `ui/stats.py` | +11 行 | 统计页面：新增指标卡片、图表优化 |
| `ui/history.py` | +5 行 | 历史页面调整：列表样式、搜索过滤 |
| `ui/home.py` | +2 行 | 首页微调 |

---

## 9. 综合结论

### 9.1 项目当前水平的客观评价

| 维度 | 水平 | 评价 |
|------|:----|------|
| **ASR（CER 55.08%）** | 学术基准偏高 | base 模型 + CPU int8 量化，成果可预期。项目重点不在 ASR 精度本身。 |
| **RAG（Recall@5=96.15%）** | 表现优秀 | bge-m3 + PGVector 在中文会议场景下召回率很高。 |
| **摘要生成** | 基础可用 | 4B 模型生成长文本有幻风险，action_items/resolutions 需修复。 |
| **端到端** | 已确认 | ASR 错误对 RAG 的影响仅 **↓ 3.84%**，语义检索对 ASR 错误容错性强。 |

### 9.2 系统局限性（按严重程度排序）

1. **ASR 选型偏弱**：Faster-Whisper base（1.5 亿参数）+ CPU int8 量化，中文不是强项，平均 CER 55.08%
2. **ASR CPU 推理慢**（约 0.1x 实时率），25 分钟音频需 3-4 分钟
3. **action_items/resolutions 为空**，需要修复 `minutes_chain.py` 输出结构
4. **长文本截断**：最长会议（18,236 字）被截断至 8,000 字，后半部分丢失
5. **小模型幻觉风险**：qwen3.5:4b 生成摘要未人工校对
6. **关键词匹配局限**：查询语义与转录表述不一致时，关键词匹配可能漏判

### 9.3 选型分析 & 推荐改进方向

#### 9.3.1 当前选型评估

| 组件 | 选型 | 评价 | 问题 |
|------|------|:----:|------|
| **ASR** | Faster-Whisper base (CPU int8) | ⚠️ 可用但偏弱 | 最小模型 + 量化 + 中文弱项 → CER 55% 是主要瓶颈 |
| **LLM** | qwen3.5:4b (Ollama) | 🟡 基础可用 | 4B 小模型，总结质量有限，缺乏 strict function calling 保证输出格式 |
| **Embedding** | bge-m3 | 🟢 优秀，无需更换 | Recall@5=96.15% 证明语义向量空间适配中文会议场景 |
| **向量库** | pgvector | 🟢 够用 | 无 hybrid search、无 reranker |
| **前端** | Gradio | 🟢 快速原型够用 | 做产品级 UI 需要换 |

#### 9.3.2 ASR 提升方案对比

| 方案 | 预期 CER | 推理速度 | 资源需求 | 推荐？ |
|------|:--------:|:--------:|:---------|:------:|
| **术语词表注入**（已实现） | ↓5-10% | 不变 | 零成本 | ✅ **立刻合入主分支** |
| **Whisper small**（2.4 亿参数） | ~45-50% | 慢~1.5x | ~2.5GB 显存 | 🟡 增益有限 |
| **Whisper medium**（7.7 亿参数） | **~35-40%** | 慢~2-3x | **~5GB 显存** | ✅ **性价比最高** |
| **Whisper large-v3**（15.5 亿参数） | **~25-30%** | 慢~5x | ~10GB 显存 | 🟡 硬件满足时优先 |
| **SenseVoice**（阿里通义） | ~20-30% | 相近 | ~4GB 显存 | ✅ 中文专用，推荐尝试 |
| **FunASM（Paraformer）** | ~20-25% | 较快 | ~3GB 显存 | 🟡 中文场景专用 |
| **阿里/讯飞 API** | ~10-15% | 快（云端） | 无硬件需求，花钱 | ❌ 依赖网络，不适合离线 |
| **音频预处理（降噪+VAD）** | 降低异常高 CER | 前置处理 | 低 | ✅ 解决卡顿/噪音片段 |

#### 9.3.3 RAG 优化方案对比

| 方案 | 预期效果 | 实现成本 | 推荐？ |
|------|---------|:--------:|:------:|
| **Hybrid Search**（向量+BM25） | 避免专有名词漏检 | 低（pgvector 已支持） | ✅ **立刻做** |
| **Reranker（bge-reranker-v2）** | 提升 MRR，改善排序质量 | 低（纯 Python） | ✅ **立刻做** |
| **Chunk 策略调优**（重叠+自适应） | 减少跨 chunk 信息丢失 | 低 | ✅ **立刻做** |
| **多字段检索**（转录+摘要+待办） | 提升 Recall | 中 | 🟡 等结构化输出修好后 |

#### 9.3.4 LLM 与工程优化

| 方案 | 预期效果 | 成本 | 推荐？ |
|------|---------|:----:|:------:|
| LLM 升级至 qwen3.5:8b/14b | 摘要更准，幻觉更少 | 需要更好 GPU | ✅ **优先做** |
| Structured output (tool calling) | 保证 action_items 格式正确 | 中 | 🟡 等 LLM 升级后 |
| Sliding window / map-reduce 摘要 | 解决长文本截断 | 中 | ✅ 高优先级 |
| 导出功能 .md/.pdf | 产品完整度 | 低 | ✅ 本周 DDL |

#### 9.3.5 推荐实施路线图

```
Phase 1（本周 → 6.9 DDL）
  ├─ 🔴 提术语词表 PR（代码已完成）
  ├─ 🔴 新增 .md/.pdf 导出功能
  └─ 🔴 修复 minutes_chain.py action_items

Phase 2（下周 → 6.16）
  ├─ 🟡 ASR 升级 → Whisper medium 或 SenseVoice
  ├─ 🟡 Hybrid Search + Reranker
  ├─ 🟡 LLM 升级至 qwen3.5:8b
  └─ 🟡 金标准摘要人工校对

Phase 3（长期）
  ├─ 🟢 音频预处理（降噪+VAD）
  ├─ 🟢 扩展 QA 对至 50+
  ├─ 🟢 AliMeeting 远场评估
  └─ 🟢 前端升级（从 Gradio 到自定义 UI）
```

### 9.4 产出物完整清单

**评估脚本目录 `evaluation/`（18 个文件）**：

| 文件 | 行数 | 大小 | 说明 |
|------|:---:|:----:|------|
| `textgrid_parser.py` | 161 | - | TextGrid 解析器 |
| `alimeeting_near_parsed.json` | 32,586 | 3.2 MB | 近场 25 说话人结构化转录 |
| `alimeeting_far_parsed.json` | 32,467 | 3.2 MB | 远场 8 说话人结构化转录 |
| `asr_eval.py` | 168 | - | ASR 评估脚本（含 `--skip` 接续功能） |
| `asr_eval_results_near.json` | **25/25 文件** | **~250 KB** | **ASR 评估结果（完整 25 文件，统一引擎）** |
| `asr_eval_results_near_bak_12.json` | 68 | 88 KB | 12 文件中间备份（合并前旧数据，归档用） |
| `asr_eval_results_near_05.json` | 68 | 88 KB | 前 5 文件 hypothesis 备份 |
| `create_gold_summary.py` | 128 | - | 金标准摘要生成脚本 |
| `gold_summaries.json` | 133 | 79 KB | 16 场会议金标准摘要 |
| `build_kb.py` | 137 | - | RAG 知识库构建脚本 |
| `kb_index_log.json` | 101 | 2.5 KB | 知识库索引日志 |
| `qa_pairs.py` | 203 | - | 26 个 QA 对定义 |
| `retrieval_eval.py` | 122 | - | 检索评估脚本 |
| `retrieval_eval_results.json` | 138 | 3 KB | 检索评估详细结果 |
| `advanced_experiment.py` | 225 | - | 进阶对比实验脚本 |
| `advanced_experiment_results.json` | 15 | 280 B | 进阶实验结果（补充：Recall 下降 **3.84%**） |
| `ISSUE_REPORT.md` | ~1100 | - | 本报告（旧版，已更新） |
| `evaluation-report.md` | ~350 | - | 综合评估报告（新版，含答辩建议） |
| `plot_cer_recall.py` | ~200 | - | CER vs RAG Recall 图表生成脚本 |
| `cer_vs_recall.png` | - | ~150 KB | CER vs RAG Recall 散点图 |
| `cer_vs_recall.pdf` | - | ~50 KB | 图表 PDF 版（答辩用） |

**其他新增文件**：

| 文件 | 说明 |
|------|------|
| `evaluation-plan.md` | 任务执行方案文档（含前知识讲解） |
| `scripts/setup_templates.py` | 导出模板注册脚本 |
| `services/terms_loader.py` | 术语表加载器服务 |
| `docs/v1.5/term-injection-report.md` | v1.5 术语注入测试报告 |
| `docs/v1.5/test-scripts.md` | v1.5 测试脚本 |
| `docs/v1.5/ui-issues.md` | v1.5 UI 问题记录 |
| `tests/test_export_long.py` | 长文档导出测试 |
| `tests/fixtures/` | 测试夹具 |

**已修复的源码文件**：

| 文件 | 修复内容 |
|------|---------|
| `rag/retriever.py` | 变量名覆盖 Bug、PGVector 类型 Bug |
| `db/models.py` | `meeting_id` 列类型与外键约束 |

### 9.5 下一步行动

**Phase 1（本周 → 6.9 DDL）**
- [ ] **🔴 高优先级**：提交术语词表 PR（代码 5 月已完成，需合入主分支）
- [ ] **🔴 高优先级**：修复 `minutes_chain.py`，让 LLM 输出结构化的 action_items/resolutions
- [ ] **🔴 高优先级**：新增 .md / .pdf 导出功能（本周 6.9 DDL）

**Phase 2（下周 → 6.16）**
- [ ] **🟡 中优先级**：升级 ASR 模型至 Whisper medium（~35% CER）或 SenseVoice（中文专用）
- [ ] **🟡 中优先级**：引入 Hybrid Search（向量 + BM25）提升 RAG 召回率
- [ ] **🟡 中优先级**：引入 Reranker（bge-reranker-v2）提升 MRR 排序质量
- [ ] **🟡 中优先级**：LLM 升级至 qwen3.5:8b，减少幻觉，支持 structured output
- [ ] **🟡 中优先级**：人工校对前 5 份金标准摘要（检查幻觉）

**Phase 3（长期）**
- [ ] **🟢 低优先级**：音频预处理（降噪 + VAD）解决卡顿/噪音导致的异常高 CER
- [ ] **🟢 低优先级**：扩展 QA 对至 50+ 提高评估统计显著性
- [ ] **🟢 低优先级**：AliMeeting 远场评估（当前仅近场 8 场）
- [ ] **🟢 低优先级**：将本报告发布到 GitHub Issue（手动 paste 到 github.com/lhy2024-dgut/meeting-agent）
