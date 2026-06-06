# RAG 检索优化 — 技术实现文档

> **作者**: @yhw028　|　**日期**: 2026-06-05　|　**关联任务**: Week 3 Sprint — 检索优化

---

## 一、优化背景

### 原有问题

项目原来的 RAG 检索是**纯向量检索**：用户查询 → bge-m3 Embedding → PGVector 余弦相似度排序 → 返回 Top-K。

这种方案有两个明显短板：

1. **精确匹配弱**：用户问"Q3 预算多少"，向量检索可能返回语义相近但不含"Q3"和"预算"的段落
2. **排序粗糙**：Bi-Encoder 分别编码 query 和 document，无法捕捉 query-document 之间的细粒度交互

### 优化方案

| 方案 | 解决什么问题 | 预期提升 |
|---|---|---|
| **Reranker** | 对召回结果二次精排，提升排序质量 | Recall@5 +5~15% |
| **Hybrid Search** | BM25 关键词检索 + 向量检索互补 | Recall@5 +10~30% |
| 两者叠加 | 精确匹配 + 语义理解 + 精排 | Recall@5 +20~40% |

---

## 二、Reranker 原理

### Bi-Encoder vs Cross-Encoder

```
Bi-Encoder（向量检索用的）：
  Query → Encoder → vec_q ─┐
                            ├→ 余弦相似度 → score
  Doc   → Encoder → vec_d ─┘

  特点：query 和 doc 分别编码，快（可预计算 doc 向量），但精度有限

Cross-Encoder（Reranker 用的）：
  [CLS] Query [SEP] Doc [SEP] → Encoder → [CLS] → Linear → score

  特点：query 和 doc 联合编码，能捕捉 token 级交互，精度高，但慢
```

### 两阶段检索范式

```
第一阶段（召回）: Query → Bi-Encoder → 向量检索 Top-20（快，~10ms）
第二阶段（精排）: (Query, Doc_i) → Cross-Encoder → 重排序 Top-5（慢，~100ms）
```

我们用的是 **BGE-Reranker-v2-m3**（BAAI 出品），特点：
- 多语言支持（100+ 语言），中文效果优异
- 模型体积 ~500MB，CPU 可跑
- 单次推理 ~100ms，对问答场景完全可接受

---

## 三、Hybrid Search 原理

### 为什么需要混合检索？

| 检索方式 | 擅长 | 不擅长 |
|---|---|---|
| **向量检索（Dense）** | 语义理解："会议讨论了什么" → 能找到"议题"相关段落 | 精确匹配：人名、数字、项目名 |
| **BM25（Sparse）** | 精确匹配："张三" → 能找到包含"张三"的段落 | 语义理解：同义词、近义词 |

两者互补，融合后覆盖更全。

### RRF（Reciprocal Rank Fusion）融合公式

```
对于文档 d，其 RRF 分数为：
  score(d) = Σ 1/(k + rank_i(d))

其中：
  - k = 60（常数，论文推荐值）
  - rank_i(d) = 文档 d 在第 i 路检索中的排名（从 1 开始）
  - Σ 对所有检索路径求和

示例：
  文档 A 在向量检索排第 1，BM25 排第 3：
    score(A) = 1/(60+1) + 1/(60+3) = 0.0164 + 0.0159 = 0.0323

  文档 B 在向量检索排第 5，BM25 排第 1：
    score(B) = 1/(60+5) + 1/(60+1) = 0.0154 + 0.0164 = 0.0318

  → 文档 A 排在文档 B 前面
```

### BM25 实现选择

| 方案 | 优点 | 缺点 | 我们的选择 |
|---|---|---|---|
| PostgreSQL tsvector + zhparser | 原生 DB 级，性能好 | 需安装 pg 扩展 | ❌ |
| **jieba + rank_bm25（应用层）** | **零 DB 运维，代码可控** | 数据量大时占内存 | ✅ |

选择应用层方案的理由：团队项目，运维成本优先，会议数据量不大（千级 chunk），内存完全够用。

---

## 四、代码改动说明

### 新增文件

#### `rag/bm25_index.py` — BM25 索引模块

```
BM25Index 类：
├── add_documents(meeting_id, chunks)  # 添加 chunks 到索引（覆盖语义）
├── remove_meeting(meeting_id)         # 移除指定会议
├── search(query, top_k, filters...)   # BM25 检索
├── clear()                            # 清空全部
└── _tokenize(text)                    # jieba 分词

单例模式：get_bm25_index()
```

核心设计：
- 每个 chunk 作为一个文档，jieba 分词后构建 BM25Okapi 倒排索引
- 脏标记法：add/remove 后置 BM25 实例为 None，下次 search 时自动重建
- `add_documents` 自动先 remove 旧数据（覆盖语义，与向量索引一致）
- 支持按 `meeting_id / meeting_ids / exclude_meeting_id / chunk_type` 限定子语料
- **全库检索复用缓存 BM25 实例**；只有子语料检索时才临时重建 BM25Okapi

#### `rag/reranker.py` — Reranker 模块

```
Reranker 类：
├── __init__(model_name)       # 加载 transformers CrossEncoder 模型
└── rerank(query, results, top_k)  # 对 (query, doc) 对打分并重排序

单例模式：get_reranker()
降级兜底：DummyReranker（模型加载失败时透传原结果）
```

实现说明：
- 当前未使用 `FlagEmbedding`
- 实际实现是 `transformers.AutoTokenizer + AutoModelForSequenceClassification`
- `rerank()` 会复制输入结果后再写入 `rerank_score`，避免污染调用方原始 `results`

### 修改文件

#### `rag/retriever.py` — 核心检索器

主要改动：

1. **`search()` 新增参数**：
   - `mode`: `"vector"` | `"bm25"` | `"hybrid"`，默认读 `config.SEARCH_MODE`
   - `enable_reranker`: 是否启用 Reranker，默认读 `config.RERANKER_ENABLED`

2. **新增内部方法**：
    - `_vector_search()`: 原纯向量检索逻辑
    - `_bm25_search()`: 委托给 BM25Index
    - `_hybrid_search()`: 向量 + BM25 双路召回 → RRF 融合
    - `_build_filters()`: 同时产出 SQL 过滤条件和结构化 BM25 过滤条件

3. **索引同步**：
    - `rebuild_meeting_index()` 完成后自动同步更新 BM25 索引
    - `remove_meeting()` 同时删除向量索引和 BM25 索引
    - 初始化时从 DB 加载已有 chunks 到 BM25 索引（`_load_bm25_from_db`）

4. **懒加载**：
   - `bm25_index` 属性：首次访问时初始化并从 DB 加载
   - `_get_reranker()` 方法：首次调用时加载模型

#### `config.py` — 新增配置项

```python
SEARCH_MODE = "hybrid"                    # 检索模式: vector | bm25 | hybrid
RERANKER_ENABLED = True                   # Reranker 开关
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"  # Reranker 模型名
MIN_SCORE_THRESHOLD = 0                  # 初排分数阈值
MIN_RERANK_SCORE = 0                     # 精排分数阈值
RECALL_MULTIPLIER = 4                    # hybrid 双路召回放大倍数
```

#### `requirements.txt` — 新增依赖

```
transformers    # CrossEncoder 模型加载
rank_bm25       # BM25 算法
jieba           # 中文分词
torch           # transformers 推理依赖
```

#### `main.py` — CLI 命令增强

- `search` 命令新增 `--mode` 和 `--no-reranker` 参数
- `eval-rag` 命令支持 `--compare / --reranker / --no-reranker`
- `eval-rag --compare` 可一键对比 `vector / bm25 / hybrid / hybrid+reranker`
- 内置评估集支持 `match=any/all`，避免单靠高频关键词导致 Recall 虚高

---

## 五、使用方式

### 切换检索模式

**方式一：环境变量（全局生效）**
```bash
# .env 文件
SEARCH_MODE=hybrid          # vector | bm25 | hybrid
RERANKER_ENABLED=true       # true | false
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
MIN_SCORE_THRESHOLD=0
MIN_RERANK_SCORE=0
RECALL_MULTIPLIER=4
```

**方式二：CLI 命令（临时测试）**
```bash
# 纯向量检索
python main.py search --mode vector "Q3预算"

# BM25 关键词检索
python main.py search --mode bm25 "张三 负责"

# Hybrid 混合检索（默认）
python main.py search --mode hybrid "会议决议"

# 关闭 Reranker
python main.py search --mode hybrid --no-reranker "议题"
```

**方式三：代码调用**
```python
from rag.retriever import get_retriever

retriever = get_retriever()

# 默认模式（读 config.SEARCH_MODE）
results = retriever.search("Q3预算")

# 指定模式
results = retriever.search("Q3预算", mode="hybrid")

# 关闭 Reranker
results = retriever.search("Q3预算", mode="hybrid", enable_reranker=False)
```

### 评估对比

```bash
# 单模式评估
python main.py eval-rag --mode hybrid

# 强制开启 Reranker
python main.py eval-rag --mode hybrid --reranker

# 检索/重排组合对比
python main.py eval-rag --compare

# 自定义评估集
python main.py eval-rag --compare eval_set.json
```

---

## 六、维护要点

### 1. 检索链路边界

- `Retriever.search()` 是统一入口，负责模式分发、阈值过滤、Reranker 开关
- `_vector_search()` 只负责 PGVector 检索
- `_bm25_search()` 只负责把结构化过滤条件传给 `BM25Index`
- `_hybrid_search()` 负责双路召回与 RRF 融合，不负责精排
- `Reranker` 永远是召回后的第二阶段，不能替代第一阶段召回

### 2. 过滤条件不要重复造一套

- SQL 检索和 BM25 检索共用 `_build_filters()`
- `_build_filters()` 当前同时返回：
  - SQL `conditions`
  - SQL `params`
  - BM25 `bm25_filters`
- 不要再通过解析 SQL 字符串反推 BM25 过滤条件，这会导致实现耦合和静默失效

### 3. BM25 索引同步规则

- `rebuild_meeting_index()` 后必须同步刷新 BM25 索引
- `remove_meeting()` 后必须同步删除 BM25 文档
- 全库检索复用缓存 `_get_bm25()`
- 子语料检索临时重建 BM25，这个成本是为了保证 scoped retrieval 正确性

### 4. Reranker 降级语义

- 模型加载失败时会自动降级到 `DummyReranker`
- 降级不影响基础 `vector / bm25 / hybrid` 检索可用性
- 如果线上发现 `rerank_score` 缺失，先看是否进入降级路径，而不是先怀疑召回逻辑

---

## 七、检索流程图

### Hybrid Search + Reranker 完整流程

```
用户查询: "Q3 预算方案谁负责"
        │
        ├──────────────────────────┐
        ▼                          ▼
   bge-m3 Embedding           jieba 分词
        │                          │
        ▼                          ▼
   PGVector 向量检索            BM25 关键词检索
   (Top-20, ~10ms)            (Top-20, ~5ms)
        │                          │
        └────────┬─────────────────┘
                 ▼
          RRF 融合 (k=60)
          score(d) = Σ 1/(60 + rank_i(d))
                 │
                 ▼
          Top-20 融合结果
                 │
                 ▼
          BGE-Reranker 精排
          (Cross-Encoder, ~100ms)
                 │
                 ▼
          Top-5 最终结果
                 │
                 ▼
          返回给用户 / 注入 LLM
```

---

## 八、后续工作

- [ ] 补充 Recall@5 对比数据（需要有会议数据入库后才能评估）
- [ ] 调优 RRF 常数 k（当前用论文推荐值 60）
- [ ] 将 `eval-rag` 从关键词命中评估逐步升级为人工标注 relevance set
- [ ] 评估 Reranker 对端到端问答质量的影响（不仅看检索指标，也看最终答案质量）
