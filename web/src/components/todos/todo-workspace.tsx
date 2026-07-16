"use client";

import { useMemo, useState } from "react";

import { Card } from "@/components/ui/cards";
import { createTodo, getTodoLogs, updateTodo, updateTodoStatus } from "@/lib/api";
import { MeetingSummary, TodoItem, TodoStatusLog } from "@/types/api";

type TodoWorkspaceProps = {
  initialTodos: TodoItem[];
  meetings?: MeetingSummary[];
  meetingId?: number;
  title?: string;
  compact?: boolean;
};

type Filters = {
  status: "all" | TodoItem["status"];
  priority: "all" | TodoItem["priority"];
};

type TodoCreatePayload = {
  content: string;
  assignee?: string;
  dueDate?: string;
  priority: TodoItem["priority"];
};

type TodoUpdatePayload = {
  content?: string;
  assignee?: string | null;
  due_date?: string | null;
  priority?: TodoItem["priority"];
};

const DEFAULT_FILTERS: Filters = {
  status: "all",
  priority: "all",
};

const TODO_STATUS_LABELS: Record<TodoItem["status"], string> = {
  pending: "待处理",
  done: "已完成",
  cancelled: "已取消",
};

const TODO_PRIORITY_LABELS: Record<TodoItem["priority"], string> = {
  high: "高优先级",
  medium: "中优先级",
  low: "低优先级",
};

export function TodoWorkspace({
  initialTodos,
  meetings = [],
  meetingId,
  title = "待办事项",
  compact = false,
}: TodoWorkspaceProps) {
  const [todos, setTodos] = useState(initialTodos);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);

  const meetingMap = useMemo(
    () => new Map(meetings.map((item) => [item.id, item])),
    [meetings],
  );

  const visibleTodos = useMemo(
    () =>
      todos.filter((item) => {
        if (filters.status !== "all" && item.status !== filters.status) {
          return false;
        }
        if (filters.priority !== "all" && item.priority !== filters.priority) {
          return false;
        }
        return true;
      }),
    [filters, todos],
  );

  async function handleCreate(payload: TodoCreatePayload) {
    if (!meetingId) {
      return;
    }

    setCreating(true);
    setError("");
    try {
      const created = await createTodo(meetingId, {
        content: payload.content,
        assignee: payload.assignee || null,
        due_date: payload.dueDate || null,
        priority: payload.priority,
      });
      setTodos((current) => [created, ...current]);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "创建待办失败");
    } finally {
      setCreating(false);
    }
  }

  async function mutateTodo(
    todoId: number,
    updater: (item: TodoItem) => Promise<TodoItem>,
  ) {
    setError("");
    const target = todos.find((item) => item.id === todoId);
    if (!target) {
      return;
    }

    try {
      const updated = await updater(target);
      setTodos((current) =>
        current.map((item) => (item.id === todoId ? updated : item)),
      );
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "更新待办失败");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="section-card-title !mb-1">{title}</h2>
          <div className="text-[13px] text-[var(--text-secondary)]">
            {compact ? "在当前会议内维护任务状态。" : "跨会议查看和维护你的结构化待办。"}
          </div>
        </div>
        {!compact ? (
          <div className="flex flex-wrap gap-2">
            <select
              className="input-shell !w-auto min-w-[140px]"
              value={filters.status}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  status: event.target.value as Filters["status"],
                }))
              }
            >
              <option value="all">全部状态</option>
              <option value="pending">待处理</option>
              <option value="done">已完成</option>
              <option value="cancelled">已取消</option>
            </select>
            <select
              className="input-shell !w-auto min-w-[140px]"
              value={filters.priority}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  priority: event.target.value as Filters["priority"],
                }))
              }
            >
              <option value="all">全部优先级</option>
              <option value="high">高优先级</option>
              <option value="medium">中优先级</option>
              <option value="low">低优先级</option>
            </select>
          </div>
        ) : null}
      </div>

      {meetingId ? (
        <TodoCreateForm
          onCreate={handleCreate}
          creating={creating}
          compact={compact}
        />
      ) : null}

      {error ? <div className="error-inline">{error}</div> : null}

      {visibleTodos.length === 0 ? (
        <Card>
          <div className="empty-inline">暂无符合条件的待办事项。</div>
        </Card>
      ) : (
        <div className="space-y-3">
          {visibleTodos.map((todo) => (
            <TodoRow
              key={todo.id}
              todo={todo}
              compact={compact}
              meetingTitle={meetingMap.get(todo.meeting_id)?.title ?? null}
              onUpdate={(payload) =>
                mutateTodo(todo.id, () => updateTodo(todo.id, payload))
              }
              onStatusChange={(status) =>
                mutateTodo(todo.id, () =>
                  updateTodoStatus(todo.id, {
                    status,
                    changed_by: "manual",
                  }),
                )
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function TodoCreateForm({
  onCreate,
  creating,
  compact,
}: {
  onCreate: (payload: TodoCreatePayload) => Promise<void>;
  creating: boolean;
  compact: boolean;
}) {
  const [content, setContent] = useState("");
  const [assignee, setAssignee] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [priority, setPriority] = useState<TodoItem["priority"]>("medium");

  async function submit() {
    const trimmed = content.trim();
    if (!trimmed) {
      return;
    }

    await onCreate({
      content: trimmed,
      assignee: assignee.trim() || undefined,
      dueDate: dueDate || undefined,
      priority,
    });
    setContent("");
    setAssignee("");
    setDueDate("");
    setPriority("medium");
  }

  return (
    <Card className="space-y-3">
      <div className="grid gap-3 md:grid-cols-4">
        <input
          className={`input-shell ${compact ? "md:col-span-2" : "md:col-span-2"}`}
          value={content}
          onChange={(event) => setContent(event.target.value)}
          placeholder="新增待办内容"
        />
        <input
          className="input-shell"
          value={assignee}
          onChange={(event) => setAssignee(event.target.value)}
          placeholder="负责人"
        />
        <input
          className="input-shell"
          type="date"
          value={dueDate}
          onChange={(event) => setDueDate(event.target.value)}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <select
          className="input-shell !w-auto min-w-[160px]"
          value={priority}
          onChange={(event) =>
            setPriority(event.target.value as TodoItem["priority"])
          }
        >
          <option value="high">高优先级</option>
          <option value="medium">中优先级</option>
          <option value="low">低优先级</option>
        </select>
        <button
          className="primary-button"
          type="button"
          onClick={() => void submit()}
          disabled={creating}
        >
          {creating ? "创建中..." : "新增待办"}
        </button>
      </div>
    </Card>
  );
}

function TodoRow({
  todo,
  compact,
  meetingTitle,
  onUpdate,
  onStatusChange,
}: {
  todo: TodoItem;
  compact: boolean;
  meetingTitle: string | null;
  onUpdate: (payload: TodoUpdatePayload) => Promise<void>;
  onStatusChange: (status: TodoItem["status"]) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState(todo.content);
  const [assignee, setAssignee] = useState(todo.assignee ?? "");
  const [dueDate, setDueDate] = useState(todo.due_date ? todo.due_date.slice(0, 10) : "");
  const [priority, setPriority] = useState<TodoItem["priority"]>(todo.priority);
  const [logs, setLogs] = useState<TodoStatusLog[] | null>(null);
  const [logsOpen, setLogsOpen] = useState(false);

  async function saveEdits() {
    await onUpdate({
      content: content.trim(),
      assignee: assignee.trim() || null,
      due_date: dueDate || null,
      priority,
    });
    setEditing(false);
  }

  async function toggleLogs() {
    if (!logsOpen && logs === null) {
      const response = await getTodoLogs(todo.id);
      setLogs(response.items);
    }
    setLogsOpen((current) => !current);
  }

  return (
    <Card className={`todo-card todo-card-${todo.status}`}>
      <div className="space-y-3">
        {/* 顶部行：左侧两个标签竖排成一列，右侧按钮横向排开 */}
        <div className="flex w-full flex-wrap items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <span className={`todo-status-badge todo-status-${todo.status} w-fit`}>
              {TODO_STATUS_LABELS[todo.status]}
            </span>
            <span className={`todo-priority-badge todo-priority-${todo.priority} w-fit`}>
              {TODO_PRIORITY_LABELS[todo.priority]}
            </span>
            {!compact && meetingTitle ? (
              <span className="todo-meeting-badge w-fit">{meetingTitle}</span>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {editing ? (
              <>
                <button className="secondary-button" type="button" onClick={() => setEditing(false)}>
                  取消
                </button>
                <button className="primary-button" type="button" onClick={() => void saveEdits()}>
                  保存
                </button>
              </>
            ) : (
              <>
                <button className="secondary-button" type="button" onClick={() => setEditing(true)}>
                  编辑
                </button>
                {todo.status !== "cancelled" ? (
                  <button className="tertiary-button" type="button" onClick={() => void onStatusChange("cancelled")}>
                    取消待办
                  </button>
                ) : (
                  <button className="tertiary-button" type="button" onClick={() => void onStatusChange("pending")}>
                    恢复待办
                  </button>
                )}
                <button className="secondary-button" type="button" onClick={() => void toggleLogs()}>
                  {logsOpen ? "收起日志" : "查看日志"}
                </button>
              </>
            )}
          </div>
        </div>

        {editing ? (
          <>
            {/* 待办内容输入框：独占一行，占满整个待办框宽度 */}
            <textarea
              className="input-shell w-full min-h-[120px]"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="待办内容"
            />
            {/* 负责人 / 日期 / 优先级：占满宽度的一行 */}
            <div className="grid w-full gap-3 sm:grid-cols-3">
              <input
                className="input-shell"
                value={assignee}
                onChange={(event) => setAssignee(event.target.value)}
                placeholder="负责人"
              />
              <input
                className="input-shell"
                type="date"
                value={dueDate}
                onChange={(event) => setDueDate(event.target.value)}
              />
              <select
                className="input-shell"
                value={priority}
                onChange={(event) => setPriority(event.target.value as TodoItem["priority"])}
              >
                <option value="high">高优先级</option>
                <option value="medium">中优先级</option>
                <option value="low">低优先级</option>
              </select>
            </div>
            {/* 完成状态切换 */}
            <label className="flex w-fit cursor-pointer items-center gap-2 text-[14px] text-[var(--text)]">
              <input
                type="checkbox"
                checked={todo.status === "done"}
                onChange={() => void onStatusChange(todo.status === "done" ? "pending" : "done")}
              />
              标记为已完成
            </label>
          </>
        ) : (
          <>
            {/* 待办内容：独占一行，占满整个待办框宽度 */}
            <div
              className={`todo-main-text w-full break-words ${
                todo.status === "done" ? "todo-main-text-done" : ""
              }`}
            >
              {todo.content}
            </div>
            <div className="flex flex-wrap gap-4 text-[13px] text-[var(--muted)]">
              <span>负责人：{todo.assignee || "未指定"}</span>
              <span>截止：{todo.due_date ? todo.due_date.slice(0, 10) : "未指定"}</span>
            </div>
          </>
        )}

      {logsOpen ? (
        <div className="todo-log-panel">
          {logs && logs.length > 0 ? (
            logs.map((item) => (
              <div key={item.id} className="todo-log-item">
                <div className="font-semibold text-[var(--dark)]">
                  {item.from_status
                    ? `${item.from_status} -> ${item.to_status}`
                    : item.to_status}
                </div>
                <div className="text-[12px] text-[var(--muted)]">
                  {item.changed_by} ·{" "}
                  {item.changed_at
                    ? item.changed_at.replace("T", " ").slice(0, 16)
                    : "未知时间"}
                </div>
                {item.reason ? (
                  <div className="text-[13px] text-[var(--text-secondary)]">
                    {item.reason}
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <div className="text-[13px] text-[var(--muted)]">暂无状态日志。</div>
          )}
        </div>
      ) : null}
      </div>
    </Card>
  );
}
