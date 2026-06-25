# Next.js + FastAPI 迁移并行验收总结

## 1. 结论

截至当前阶段，`C:\Users\Administrator\Desktop\meeting-agent\migration\nextjs-fastapi` 下的新前端迁移实现已经覆盖旧版 Streamlit 的核心使用链路，并完成了与旧版并行运行条件下的点击验收。

当前状态可以定义为：

- 新前端已具备独立验收能力
- 旧版 Streamlit 未被替换，仍可继续作为兜底入口
- 适合进入“并行观察 + 补零散差异 + 再决定切换”的收尾阶段

## 2. 已完成并行验收的主链路

### 首页与导航

- 首页 dashboard 信息卡片可正常展示
- 最近会议入口可跳转到会议详情页
- 可从首页进入上传、历史、统计等核心页面

### 历史页

- 历史列表分页可切换
- 搜索与筛选联动已经接入真实 API
- 删除会议链路可执行
- 项目名编辑链路可执行
- 删除交互已向旧版确认体验靠拢

### 会议详情页

- 纪要、待办、决议、转录内容可展示
- 导出下载链路可点击验收
- 重新生成纪要链路可点击验收
- 单场会议聊天链路可点击验收

### 跨会议聊天

- 跨会议问答可返回来源
- 来源列表已补“将跳到：待办第 2 条 / 决议第 1 条”这类预览
- 来源点击可跳转到对应会议详情页
- 跳转时可按片段类型高亮
- 跳转时会滚动到对应区块并闪烁
- 已支持更细粒度片段定位
- 精确定位失败时会提示已退回到对应区块
- 同会来源详情已做本地缓存，并带会话切换/5 分钟失效策略
- 开发态已补缓存命中日志/调试开关

### 上传页

- 模板列表与模板预览已补齐
- 上传完整提交流程已做纯点击验收
- 上传后可进入真实处理链路并回到详情页

### 统计页

- `/stats` 已补纯点击验收
- 可从首页点击进入统计页
- 指标卡和图表渲染已纳入自动化检查

## 3. 当前自动化验收覆盖

Playwright 用例目录：
`C:\Users\Administrator\Desktop\meeting-agent\migration\nextjs-fastapi\web\tests\e2e`

当前覆盖文件包括：

- `home-dashboard.spec.ts`
- `stats-overview.spec.ts`
- `history-filtering.spec.ts`
- `history-management.spec.ts`
- `history-pagination.spec.ts`
- `upload-template-preview.spec.ts`
- `upload-flow.spec.ts`
- `meeting-export-download.spec.ts`
- `meeting-regenerate.spec.ts`
- `single-meeting-chat.spec.ts`
- `cross-meeting-source-jump.spec.ts`

## 4. 新旧前端并行关系

当前并行方式如下：

- 旧版 Streamlit 保持原目录与原入口，不改主功能
- 新版 Next.js + FastAPI 完全放在 `migration\nextjs-fastapi` 下
- 两套前端可以分别启动、分别验收
- 当前未做默认入口切换，因此出现问题时不会阻断旧版使用

这意味着本次迁移满足最初约束：

- 新建文件夹实现
- 不影响现有功能
- 逐步迁移而不是一次性替换

## 5. 还剩什么

从“核心迁移是否完成”的角度看，主链路已经基本完成。

当前剩余工作更偏收尾，而不是主功能缺失：

- 继续补少量视觉细节与旧版逐项对照
- 根据并行观察结果决定是否切默认入口
- 如果准备正式切换，再补启动文档、部署文档和回退预案

## 6. 建议切换门槛

建议至少满足以下条件后，再讨论下线 Streamlit 主入口：

1. `npm run test:e2e:smoke` 连续稳定通过。
2. `npm run test:e2e:full` 在真实 API 环境稳定通过。
3. 人工对照旧版确认页面效果与关键交互无明显偏差。
4. 明确保留一段并行观察窗口，避免直接硬切。
