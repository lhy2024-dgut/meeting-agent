# Week 3 交付与复盘（@yhw028）

---

## 1. 本周完成内容

### 1.1 引入 Reranker

- 已新增 `rag/reranker.py`
- 已在 `rag/retriever.py` 中接入 `enable_reranker`
- 当前使用 `BAAI/bge-reranker-v2-m3`
- 支持模型加载失败时自动降级为 `DummyReranker`

**目的**

- 对第一阶段召回结果做二次排序
- 提升 query 和 chunk 之间的细粒度匹配能力
- 为后续问答质量提升提供更稳定的检索前置能力

### 1.2 实现 Hybrid Search

- 已新增 `rag/bm25_index.py`
- 已实现 `vector / bm25 / hybrid` 三种检索模式
- `hybrid` 模式采用 RRF（Reciprocal Rank Fusion）融合向量检索与 BM25 检索结果

**目的**

- 用 BM25 补齐向量检索在关键词、人名、数字、专有名词上的不足
- 用向量检索保留语义召回能力
- 提升整体召回覆盖面，而不是依赖单一路径

### 1.3 输出技术实现文档

- 已完成 [rag-optimization.md](C:/Users/Administrator/Desktop/meeting-agent/docs/rag-optimization.md)

文档已覆盖：

- 改动点
- 设计思路
- Reranker / Hybrid Search 原理
- 配置项说明
- 使用方式
- 维护要点


---

## 2. 演示功能与使用方式

### 2.1 检索调试

```bash
python main.py search --mode vector "Q3预算"
python main.py search --mode bm25 "张三 负责"
python main.py search --mode hybrid "会议决议"
python main.py search --mode hybrid --no-reranker "议题"
```

### 2.2 检索评估

```bash
python main.py eval-rag --mode hybrid
python main.py eval-rag --mode hybrid --reranker
python main.py eval-rag --compare
```

### 2.3 自动化测试

```bash
pytest -q
```

本地结果：

- `33 passed`

---

## 3. 检索对比数据

本次对比数据已落盘到：

- [rag_eval_compare.json](C:/Users/Administrator/Desktop/meeting-agent/evaluation/results/rag_eval_compare.json)

评估命令：

```bash
python main.py eval-rag --compare
```

评估条件：

- 语料规模：`265` 个 chunk
- 评估集：`main.py` 内置 5 条样例
- 指标：`Recall@5`

### 3.1 对比结果

| 模式 | Recall@5 | 命中数 |
|---|---:|---:|
| vector | 60% | 3 / 5 |
| bm25 | 80% | 4 / 5 |
| hybrid | 60% | 3 / 5 |
| hybrid + reranker | 60% | 3 / 5 |

### 3.2 当前阶段结论

1. **当前评估样例下，BM25 表现最好**
   - 说明现有测试问题更偏关键词匹配场景
   - BM25 在当前数据分布下具备明显优势

2. **Hybrid 和 Hybrid+Reranker 暂时未超过 BM25**
   - 说明当前 RRF 融合参数、评估集规模、chunk 质量或 reranker 使用策略还需要继续优化
   - 这不代表 Hybrid 路线错误，而是说明当前配置尚未释放出优势

3. **这份结果可以满足“检索任务需附对比数据”的交付要求**
   - 但它仍属于阶段性评估
   - 后续最好升级为更正式的人工标注 relevance set

---

## 4. 遇到的问题

### 4.1 当前内置评估集规模偏小

- 只有 5 条 query
- 适合作为快速回归检查
- 不足以支撑更强的统计结论

### 4.2 Hybrid 与 Reranker 优势尚未在当前数据上体现

- 当前结果显示 `bm25 > hybrid = hybrid+reranker = vector`
- 说明现有评估样例更偏向显式关键词命中
- 下一步需要扩大评估集，并引入更复杂的语义检索问题

### 4.3 检索优化与 chunk 策略仍然相互耦合

- 当前语料仍以现有 chunk 方案为基础
- 如果后续 chunk 策略调整，检索结果可能会同步变化
- 因此当前检索评估结论应理解为“在当前 chunk 条件下”的阶段性结论

---

## 5. 周一复盘会建议汇报结构

### 演示部分

1. 演示 `search --mode vector|bm25|hybrid`
2. 演示 `search --mode hybrid --no-reranker`
3. 演示 `eval-rag --compare`

### 进度同步部分

1. 已完成 Reranker 接入
2. 已完成 Hybrid Search
3. 已完成技术实现文档
4. 已补齐检索对比数据

### 问题讨论部分

1. 为什么当前 BM25 在内置评估集上最好
2. Hybrid / Reranker 为什么还没体现优势
3. 下一阶段是否要扩大评估集并引入人工标注 relevance set

---

## 6. 下一步建议

1. 扩大检索评估集，不再只依赖 5 条内置 query
2. 引入人工标注 relevance set，替代纯关键词命中评估
3. 调优 `RECALL_MULTIPLIER`、RRF 常数和 reranker 使用策略
4. 结合后续 chunk 策略对比结果，重新验证检索链路表现

---

