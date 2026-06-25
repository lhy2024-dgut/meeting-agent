# 前端迁移 Issue 报告

## 1. 范围说明

本报告针对 `Meeting Agent` 从 `Streamlit` 迁移到 `Next.js + FastAPI` 的新前端实现进行问题梳理。

相关目录：

- 前端：`C:\Users\Administrator\Desktop\meeting-agent\migration\nextjs-fastapi\web`
- 迁移 API：`C:\Users\Administrator\Desktop\meeting-agent\migration\nextjs-fastapi\api`
- 旧版入口：`C:\Users\Administrator\Desktop\meeting-agent\app.py`

本报告重点回答三个问题：

- 当前迁移实现是否已经具备基本可运行能力
- 当前仍有哪些实际问题会影响迁移落地
- 哪些日志问题属于历史问题，不应继续误判为当前阻塞项

## 2. 当前复核结论

截至本次复核，迁移前端不是“完全不可用”状态，已经具备基本运行能力：

- `Next.js` 生产构建通过：`npm run build` 已成功
- 迁移 API 可启动并响应健康检查：`GET /api/health -> {"status":"ok"}`
- 因此，历史日志中出现的部分错误，不能直接视为当前仍然存在的 blocker

但从“可稳定迁移、可切主入口”的标准看，当前仍有若干关键问题，主要集中在：

- 前端对后端可用性依赖过强
- API 异常时前端缺少降级与错误承接
- 环境配置和并行验收流程仍偏手工，复现稳定性不足
- 历史日志与当前代码状态脱节，影响问题判断

## 3. 当前确认存在的问题

### Issue 1：前端对 API 可用性存在硬依赖，后端不可用时页面会直接失败

- 严重级别：`High`
- 影响范围：`/chat`、`/meetings` 以及所有 SSR 时直接请求 API 的页面

#### 证据

前端请求封装在 [api.ts](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/src/lib/api.ts:15) 中默认走：

- `NEXT_PUBLIC_API_BASE_URL`
- 若未设置，则回退到 `http://127.0.0.1:8000/api`

请求逻辑在 [api.ts](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/src/lib/api.ts:22) 到 [api.ts](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/src/lib/api.ts:31)：

- 只要 `response.ok` 为假，就直接 `throw new Error`
- 没有页面级兜底状态，没有降级文案，也没有容错包装

例如：

- [chat/page.tsx](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/src/app/chat/page.tsx:4) 在服务端渲染阶段直接调用 `getMeetings()`
- [meetings/page.tsx](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/src/app/meetings/page.tsx:13) 也在服务端渲染阶段直接请求会议列表

历史运行日志也记录了该现象：

- [next-start.stderr.log](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/next-start.stderr.log:1) 中出现 `ECONNREFUSED 127.0.0.1:8000`

#### 影响

这意味着：

- 迁移前端虽然可构建，但运行时高度依赖后端已先启动且端口正确
- 后端一旦未启动、启动慢、端口错误或 API 临时异常，前端页面会直接报错，而不是进入“服务暂不可用”的可恢复状态
- 这种行为对并行迁移阶段尤其不友好，因为迁移期最常见的问题恰恰是服务未就绪或环境配置不一致

#### 建议

- 在 API 请求层区分“网络错误”“4xx 业务错误”“5xx 服务错误”
- 页面层增加显式错误状态和可恢复提示，而不是直接抛异常终止渲染
- 对首页、历史页、聊天页至少补一层 error boundary 或等价的错误承接方案
- 并行迁移阶段应优先保证“失败可解释”，而不是“失败直接炸页”

### Issue 2：前端将所有非 200 响应统一视为致命错误，缺少业务态处理

- 严重级别：`High`
- 影响范围：聊天、历史、详情、上传等所有 API 交互页面

#### 证据

在 [api.ts](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/src/lib/api.ts:27) 和 [api.ts](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/src/lib/api.ts:43)，前端对所有非 `ok` 响应都直接抛出：

```ts
throw new Error(`API request failed: ${response.status}`);
```

历史日志显示该逻辑已经在页面渲染中外溢：

- [web.err.log](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/logs/web.err.log:1) 中出现 `API request failed: 422`

#### 影响

- `422` 这类本可通过参数提示、空态提醒或表单修正解决的问题，当前会直接升级为页面错误
- 用户无法区分“是输入不合法”还是“系统挂了”
- 前后端联调阶段会放大排查成本，因为所有失败都被折叠成同一种前端异常

#### 建议

- 对 `400/404/422` 提供业务态处理
- 对 `500` 和网络错误保留系统错误路径
- 在聊天页、上传页、历史筛选页等高频交互页面补充可读错误文案
- 把“服务异常”和“用户输入问题”从体验层拆开

### Issue 3：默认 API 地址绑定本地 `8000`，部署与并行验收容易出现环境漂移

- 严重级别：`Medium`
- 影响范围：本地启动、并行验收、预发布部署、多人协作环境

#### 证据

[api.ts](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/src/lib/api.ts:15) 到 [api.ts](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/src/lib/api.ts:19) 中，默认 API 地址写死为：

- `http://127.0.0.1:8000/api`

同时 [README.md](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/README.md:11) 到 [README.md](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/README.md:35) 仍要求人工分别启动两套服务。

#### 影响

- 一旦 API 不在 `8000`，或者同机存在多套服务，前端会默认连错地址
- 手工启动顺序和手工注入环境变量，容易让“代码问题”和“环境问题”混在一起
- 并行迁移阶段最怕的不是单次错误，而是“同一代码在不同机器、不同启动顺序下表现不一致”

#### 建议

- 为迁移前端补标准 `.env` / `.env.local` 示例
- 给前后端并行验收补统一启动脚本
- 前端启动前增加 API 健康检查提示
- 把当前“约定式环境”改成“显式配置式环境”

### Issue 4：并行验收结论偏乐观，但复现链路仍依赖人工步骤

- 严重级别：`Medium`
- 影响范围：迁移验收可信度、后续切换决策

#### 证据

[parallel validation summary](C:/Users/Administrator/Desktop/meeting-agent/docs/nextjs-fastapi-parallel-validation-summary.md:1) 已给出“核心链路已覆盖、适合并行观察”的结论。

但从当前实际运行方式看：

- API 与前端仍需要手工分别启动
- 前端是否正常，依赖后端是否已就绪
- E2E 文档虽然存在，但当前并没有一个“单命令拉起依赖并执行冒烟验证”的固定入口

#### 影响

- 验收结论更像“某次手工验证通过”，而不是“当前代码处于可稳定重复验证状态”
- 对迁移切换来说，这种差异很关键：
  - 能跑通一次，不等于适合切换默认入口
  - 能稳定复现，才说明迁移完成度足够高

#### 建议

- 增加一键化 smoke 验证流程
- 至少固化：启动 API、等待健康检查、启动前端、执行 Playwright smoke、汇总结果
- 将“并行验收通过”的定义从文档描述升级为可执行流程

### Issue 5：历史日志与当前代码状态不一致，影响问题判断效率

- 严重级别：`Medium`
- 影响范围：故障排查、迁移状态判断、对外汇报

#### 证据

历史日志中记录过两类明显错误：

1. [api-8000.stderr.log](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/api-8000.stderr.log:1)
   - 曾出现 `ImportError: cannot import name 'DistributionItem'`
2. [web.err.log](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/logs/web.err.log:10)
   - 曾出现 `Module not found: Can't resolve '@/components/history/history-page'`

但本次复核发现：

- [stats.py](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/api/routers/stats.py:5) 当前确实已导入 `DistributionItem`
- [stats schema](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/api/schemas/stats.py:4) 当前也确实定义了 `DistributionItem`
- `npm run build` 当前已经成功通过，说明前端 `module not found` 问题至少在本次复核版本中已不存在

#### 影响

- 如果直接引用旧日志，很容易把“历史已修复问题”误判成“当前 blocker”
- 迁移报告会被历史痕迹污染，影响决策准确性
- 团队会花时间重复排查已经解决的问题

#### 建议

- 给迁移目录加按时间分离的运行日志
- 每次验收前清理旧日志或单独存档
- 在 issue 文档中明确区分：
  - 当前仍存在的问题
  - 历史出现、现已复核通过的问题

## 4. 历史出现但本次复核未复现的问题

以下问题在历史日志里出现过，但本次复核中不应继续直接作为当前阻塞项使用：

### 4.1 `DistributionItem` ImportError

- 历史证据： [api-8000.stderr.log](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/api-8000.stderr.log:1)
- 当前复核结果：
  - [stats.py](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/api/routers/stats.py:5) 可正常引用 `DistributionItem`
  - [stats schema](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/api/schemas/stats.py:4) 已存在该定义
  - API 当前可启动，`/api/health` 可访问

结论：

- 该问题更可能属于历史版本、旧环境或旧日志残留
- 不建议继续作为“当前未解决问题”写入结论部分

### 4.2 `@/components/history/history-page` module not found

- 历史证据： [web.err.log](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/logs/web.err.log:10)
- 当前复核结果：
  - [meetings/page.tsx](C:/Users/Administrator/Desktop/meeting-agent/migration/nextjs-fastapi/web/src/app/meetings/page.tsx:1) 当前引用正常
  - `npm run build` 已成功通过

结论：

- 该问题至少在当前代码状态下已不再构成阻塞
- 可以在 issue 报告中保留为“历史曾发生问题”，但不应写成当前 blocker

## 5. 迁移状态判断

基于本次复核，更准确的判断不是“迁移失败”，也不是“迁移已完全完成”，而是：

- 前端迁移主干能力已经落地
- 基本构建与 API 启动能力已具备
- 当前主要问题已经从“代码骨架缺失”转为“运行时韧性不足、验收链路不够工程化”

因此，当前更适合的阶段定义应为：

- `可以继续并行验证`
- `暂不建议直接切主入口`

## 6. 建议优先级

### 第一优先级

- 处理 API 不可用时的前端硬失败问题
- 处理 4xx/5xx 全部统一抛异常的问题
- 给关键页面补可恢复错误态

### 第二优先级

- 标准化环境变量与启动方式
- 增加统一的 smoke 验收入口
- 减少“靠人工记忆”的并行启动流程

### 第三优先级

- 清理或归档旧日志
- 把历史故障和当前状态彻底分离
- 补正式切换前的回退与观察方案

## 7. 可对外使用的结论表述

如果这份 issue 报告需要上传或汇报，建议使用以下表述：

> 当前前端迁移版本已完成核心页面和主链路实现，生产构建与迁移 API 启动均已验证通过；但在运行时稳定性和迁移验收工程化方面仍存在问题，主要体现在前端对后端可用性的硬依赖、API 异常缺少降级处理、以及并行验收流程仍偏手工。现阶段适合继续并行观察和补齐韧性问题，暂不建议直接切换为默认入口。
