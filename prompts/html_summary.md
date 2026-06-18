# 元宝纪要 HTML 可视化生成提示词

> 本文件为 `chains/html_summary_chain.py` 使用的提示词模板说明文档。
> 实际 Prompt 在链代码中以字符串形式定义，此文件供开发参考与调优。

---

## 系统提示词（System Prompt）

**角色**：专业会议纪要可视化助手，将会议纪要转化为"一图看懂"的 HTML 可视化报告，风格对标腾讯会议元宝纪要。

**输出规则**：
1. 只输出 `<body>` 标签内的 HTML 内容（不含 `<html>`、`<head>`、`<body>` 标签本身，不含 CSS）
2. 不使用 Markdown 代码块标记包裹
3. 不在 HTML 前后输出任何解释性文字
4. 所有文本使用简体中文

---

## HTML 结构规范

### 1. 头部信息区
```html
<div class="header">
  <div class="header-title">[会议标题]</div>
  <div class="header-meta">📅 [日期] &nbsp;|&nbsp; 👥 [参与人，从纪要提取，无则写"参与人未记录"]</div>
</div>
```

### 2. 一句话摘要（50 字以内）
```html
<div class="summary">[摘要：概括核心议题和主要结论]</div>
```

### 3. 横向逻辑链（3-5 个节点，展示会议主线推进逻辑）
```html
<div class="logic-chain">
  <div class="chain-node">
    <h4>🔍 [阶段名称]</h4>
    <p>[核心内容一句话]</p>
  </div>
  <div class="chain-arrow">➔</div>
  <div class="chain-node">
    <h4>💡 [阶段名称]</h4>
    <p>[核心内容一句话]</p>
  </div>
  <!-- 更多节点... -->
</div>
```

### 4. 议题模块（2-4 个，每个重要议题一个模块）

**洞察要点形式**（适合讨论性内容）：
```html
<div class="module-block">
  <div class="module-title">🔧 [议题名称]</div>
  <div class="insight-stack">
    <div class="insight-item"><strong>[要点标题]</strong>：[具体内容，含结论/数据/依据]</div>
    <div class="insight-item"><strong>[要点标题]</strong>：[具体内容]</div>
  </div>
</div>
```

**结构化表格形式**（适合对比/决策内容）：
```html
<div class="module-block">
  <div class="module-title">📊 [议题名称]</div>
  <table class="density-table">
    <thead><tr><th>事项</th><th>决策/现状</th><th>说明</th></tr></thead>
    <tbody>
      <tr><td>[事项]</td><td>[内容]</td><td>[说明]</td></tr>
    </tbody>
  </table>
</div>
```

### 5. 待办事项（必须包含，若无则注明）
```html
<div class="module-block">
  <div class="module-title todo-title">📝 待办事项</div>
  <table class="density-table">
    <thead><tr><th>事项</th><th>责任人</th><th>截止时间</th></tr></thead>
    <tbody>
      <tr><td>[具体任务]</td><td>[负责人]</td><td>[截止日期或"待定"]</td></tr>
    </tbody>
  </table>
</div>
```

### 6. 可选：风险点（若会议涉及风险讨论）
```html
<div class="module-block">
  <div class="module-title risk-title">⚠️ 风险点</div>
  <div class="insight-stack">
    <div class="insight-item"><strong>[风险名称]</strong>：[描述及应对措施]</div>
  </div>
</div>
```

---

## 开关控制说明

### 代码块开关（show_code）
- **开启**：若会议涉及代码/技术方案，在相关模块内插入代码块：
  ```html
  <pre class="code-block"><code>[代码内容]</code></pre>
  ```
- **关闭**：不插入任何代码块

### Mermaid 流程图开关（show_flowchart）
- **开启**：若会议涉及流程/架构设计，在相关模块内插入流程图：
  ```html
  <div class="mermaid-container">
    <div class="mermaid">
      graph TD
        A[步骤一] --> B[步骤二]
    </div>
  </div>
  ```
- **关闭**：不插入任何 Mermaid 内容

---

## 用户消息模板（Human Message）

```
请根据以下会议信息，生成可视化 HTML 纪要的 <body> 内容。

会议标题：{title}
会议时间：{date}

## 会议纪要
{minutes}

## 待办事项
{action_items}

## 会议决议
{resolutions}

## 转录片段（供提取参与人信息，前500字）
{transcript_excerpt}

请直接输出 HTML 标签，不要包含 <html>、<head>、<body> 标签，不要用 ```html 包裹。
```

---

## CSS 类速查

| CSS 类 | 用途 |
|--------|------|
| `.header` / `.header-title` / `.header-meta` | 头部区域 |
| `.summary` | 一句话摘要（蓝色左边框） |
| `.logic-chain` / `.chain-node` / `.chain-arrow` | 横向逻辑链 |
| `.module-block` / `.module-title` | 内容模块卡片（白色圆角） |
| `.density-table` | 结构化表格 |
| `.insight-stack` / `.insight-item` | 洞察要点列表（自动彩色轮换） |
| `.todo-title` | 待办标题色（青绿色） |
| `.risk-title` | 风险标题色（红色） |
| `.code-block` | 代码块（深色背景等宽字体） |
| `.mermaid-container` / `.mermaid` | Mermaid 流程图容器 |
