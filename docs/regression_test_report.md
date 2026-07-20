# 会议问答、Todo、登录、统计回归测试报告

## 结论

基础服务、单元测试、前端 lint 和生产构建均可通过，但四条核心链路仍存在 **2 个 P0、4 个 P1、3 个 P2**。其中 P0 包含跨账号问答内容泄露和会议重生成导致 Todo 数据丢失，不应进入答辩演示环境。

## 验证记录

## P0

### F-001 问答历史会跨账号显示

**链路：** 登录 -> 会议问答 -> 退出 -> 另一账号登录 -> 会议问答
**位置：** `web/src/hooks/use-chat-session.ts`、`web/src/components/providers/auth-provider.tsx`

问答恢复键为 `meeting-agent-chat:${mode}:${meetingId}`，不包含用户 ID；退出逻辑只清除 Token，不清除 `sessionStorage`。因此在同一浏览器标签页中，账号 B 登录后会先恢复并显示账号 A 的问题、回答和 RAG 来源。后续发送请求虽然会被后端的会话归属校验拒绝，但敏感内容已经泄露到界面。

**复现步骤：**

1. 账号 A 在任意会议中完成至少一轮问答。
2. 不关闭标签页，执行退出并登录账号 B。
3. 进入相同单场会议或跨会议问答页。
4. 页面从 `sessionStorage` 恢复账号 A 的历史消息。

**建议修复：** 把用户 ID 加入持久化键；登出时清理所有 `meeting-agent-chat:` 条目；恢复缓存前校验其 `userId` 与当前用户一致。增加“同浏览器切换账号不显示旧问答”的 E2E 用例。

### F-002 重生成会议会删除人工维护的 Todo 与审计日志

**链路：** 会议详情 -> 人工维护 Todo -> 重新生成会议 -> Todo 闭环
**位置：** `api/routers/meetings.py:440`、`services/todo_service.py:310`

重新生成会议后调用 `sync_meeting_todos(..., replace=True)`。该路径先删除该会议全部 `todo_status_logs` 和 `todo_items`，再按新的 LLM 输出重新创建 Todo。用户新增的任务、负责人/截止日期修改、完成或取消状态和全部审计记录都会丢失。

**影响：** Todo 闭环最重要的“人工确认与可追溯性”被重新生成操作破坏。

**建议修复：** 不对人工 Todo 使用全量替换。为 Todo 增加来源标识（如 `meeting_pipeline` / `manual`）；只更新仍未人工修改的自动抽取任务，并以内容哈希或稳定 ID 做匹配。重生成前应提示将影响的自动任务数量。

## P1

### F-003 失效 Token 会导致登录入口不可达并返回首页 500

**链路：** Token 失效/撤销 -> 访问任意页面 -> 重新登录
**位置：** `web/middleware.ts`、`web/src/app/page.tsx`、`web/src/lib/api.ts`

中间件只检查 Cookie 是否存在。带无效 `meeting_agent_access_token` 访问 `/login` 时，中间件返回 `307 Location: /`；首页 SSR 再使用无效 Token 请求后端，抛出未处理的 `ApiError: Invalid or expired token`，返回 `500`。

**已复现命令：**

```powershell
curl.exe -s -D - -o NUL --max-redirs 0 `
  -H "Cookie: meeting_agent_access_token=invalid-token" `
  http://127.0.0.1:3000/login

curl.exe -s -D - -o NUL --max-redirs 0 `
  -H "Cookie: meeting_agent_access_token=invalid-token" `
  http://127.0.0.1:3000/
```

**建议修复：** 公共路由不应仅因 Cookie 存在而跳转；SSR 页面捕获 `401` 并重定向到登录页。失效时应在客户端和服务端统一清理 Cookie，避免重定向循环。

### F-004 问答会话过期或服务重启后，前端会恢复失效会话但无法自动恢复

**链路：** 会议问答 -> 闲置 30 分钟/服务重启 -> 刷新页面 -> 继续提问
**位置：** `api/services/chat_session_manager.py`、`web/src/hooks/use-chat-session.ts`

后端会在 30 分钟后删除内存会话，前端仍永久保留该会话 ID 和历史消息。刷新后页面显示旧历史，发送消息时收到 `404 Chat session not found`；当前逻辑只显示错误，不会新建会话或说明如何恢复。

**建议修复：** 当消息接口返回 `404` 时，清除本地缓存并自动创建新会话；保留可见历史但明确提示“上下文已重置”，或将会话和消息改为按用户持久化到数据库。

### F-005 Todo 状态日志的操作者可由客户端伪造

**链路：** Todo 状态变更 -> 审计日志
**位置：** `api/schemas/todos.py`、`api/routers/todos.py`、`services/todo_service.py`

`changed_by` 由请求体接收并原样写入日志。虽然前端固定发送 `manual`，任何已登录用户都可以调用接口写入 `meeting_pipeline`、`system` 或任意字符串，日志不能作为可信审计证据。

**建议修复：** 从服务端动作和当前用户生成审计字段，例如 `user:{current_user.id}`、`meeting_pipeline`；删除或限制客户端 `changed_by` 字段。

### F-006 统计环境标签与人数指标不具备可靠数据基础

**链路：** 会议处理 -> 统计页
**位置：** `services/meeting_service.py`、`services/meeting_service.py:_estimate_speaker_count_heuristic`、`engines/asr_engine.py`

环境分类使用 ASR 分段的平均时长估计说话人数：平均分段小于 15 秒即判为至少两人。普通单人语音也常被切成短段，因此“多人会议”会被系统性高估；所谓“嘈杂”来自整体响度，不等同于噪声水平。历史会议仍保留 `unknown`，使环境分布各项之和可能小于总会议数。

**建议修复：** 仅在真实说话人分离结果存在时写入 `multi_speaker`；将音量指标和环境噪声分开，无法可靠判断时使用并展示“未知”。统计 API 返回 `unknown`，前端明确显示而不是静默丢弃。

## P2

### F-007 Todo 状态日志打开后不会随状态变化刷新

**位置：** `web/src/components/todos/todo-workspace.tsx`

日志只在首次展开时加载到组件状态。随后将任务完成、取消或恢复，日志面板仍显示旧内容，直到用户刷新页面。

**建议修复：** 状态变更成功后使对应 Todo 的日志缓存失效，或将新日志乐观追加到列表。

### F-008 统计页没有反映 Todo 闭环效果

**位置：** `api/routers/stats.py`、`db/repository.py`

统计页只展示会议数量、时长、环境和月度趋势，没有待办总数、完成率、逾期数、按负责人分布等闭环指标。产品已具备 Todo 状态机，但无法量化其使用价值。



### F-009 核心四流程的端到端覆盖不完整

**位置：** `web/tests/e2e/helpers.ts`、`web/tests/e2e/`

现有 E2E 覆盖单场问答与统计渲染，但没有登录失效/退出、跨账号问答缓存、Todo 创建到状态日志再到重生成、统计口径校验。辅助脚本默认账号密码仍是 `admin/ChangeMe123!`，安全修复后会让 E2E 无法登录。
