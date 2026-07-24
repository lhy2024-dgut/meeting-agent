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
  unlockToken?: string | null;
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

const STATUS_SORT_ORDER: Record<TodoItem["status"], number> = {
  pending: 0,
  cancelled: 1,
  done: 2,
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
  unlockToken = null,
}: TodoWorkspaceProps) {
  const [todos, setTodos] = useState(initialTodos);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const privacyOptions = unlockToken
    ? { headers: { "X-Meeting-Unlock-Token": unlockToken } }
    : undefined;

  const meetingMap = useMemo(
    () => new Map(meetings.map((item) => [item.id, item])),
    [meetings],
  );

  const visibleTodos = useMemo(
    () =>
      todos
        .filter((item) => {
          if (filters.status !== "all" && item.status !== filters.status) {
            return false;
          }
          if (filters.priority !== "all" && item.priority !== filters.priority) {
            return false;
          }
          return true;
        })
        // 未完成的排在前面，已完成的排在后面（组内保持原有顺序）
        .sort((a, b) => STATUS_SORT_ORDER[a.status] - STATUS_SORT_ORDER[b.status]),
    [filters, todos],
  );

  async function handleCreate(payload: TodoCreatePayload): Promise<boolean> {
    if (!meetingId) {
      return false;
    }

    setCreating(true);
    setError("");
    try {
      const created = await createTodo(meetingId, {
        content: payload.content,
        assignee: payload.assignee || null,
        due_date: payload.dueDate || null,
        priority: payload.priority,
      }, privacyOptions);
      setTodos((current) => [created, ...current]);
      return true;
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "创建待办失败");
      return false;
    } finally {
      setCreating(false);
    }
  }

  async function mutateTodo(
    todoId: number,
    updater: (item: TodoItem) => Promise<TodoItem>,
  ): Promise<boolean> {
    setError("");
    const target = todos.find((item) => item.id === todoId);
    if (!target) {
      return false;
    }

    try {
      const updated = await updater(target);
      setTodos((current) =>
        current.map((item) => (item.id === todoId ? updated : item)),
      );
      return true;
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "更新待办失败");
      return false;
    }
  }

  async function changeTodoStatus(
    todoId: number,
    status: TodoItem["status"],
  ): Promise<boolean> {
    setError("");
    try {
      const updated = await updateTodoStatus(todoId, {
        status,
      }, privacyOptions);
      setTodos((current) =>
        current.map((item) => (item.id === todoId ? updated : item)),
      );
      return true;
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "更新待办失败");
      return false;
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
              unlockToken={unlockToken}
              onUpdate={(payload) =>
                mutateTodo(todo.id, () => updateTodo(todo.id, payload, privacyOptions))
              }
              onStatusChange={(status) => changeTodoStatus(todo.id, status)}
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
  onCreate: (payload: TodoCreatePayload) => Promise<boolean>;
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

    const created = await onCreate({
      content: trimmed,
      assignee: assignee.trim() || undefined,
      dueDate: dueDate || undefined,
      priority,
    });
    if (!created) {
      return;
    }
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
  unlockToken,
}: {
  todo: TodoItem;
  compact: boolean;
  meetingTitle: string | null;
  onUpdate: (payload: TodoUpdatePayload) => Promise<boolean>;
  onStatusChange: (status: TodoItem["status"]) => Promise<boolean>;
  unlockToken: string | null;
}) {
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState(todo.content);
  const [assignee, setAssignee] = useState(todo.assignee ?? "");
  const [dueDate, setDueDate] = useState(todo.due_date ? todo.due_date.slice(0, 10) : "");
  const [priority, setPriority] = useState<TodoItem["priority"]>(todo.priority);
  const [logs, setLogs] = useState<TodoStatusLog[] | null>(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState(false);

  async function saveEdits() {
    const updated = await onUpdate({
      content: content.trim(),
      assignee: assignee.trim() || null,
      due_date: dueDate || null,
      priority,
    });
    if (updated) {
      setEditing(false);
    }
  }

  async function toggleLogs() {
    if (!logsOpen && logs === null) {
      const response = await getTodoLogs(todo.id, {
        headers: unlockToken ? { "X-Meeting-Unlock-Token": unlockToken } : undefined,
      });
      setLogs(response.items);
    }
    setLogsOpen((current) => !current);
  }

  async function changeStatus(status: TodoItem["status"]) {
    if (statusUpdating) {
      return;
    }
    setStatusUpdating(true);
    try {
      const updated = await onStatusChange(status);
      if (updated) {
        setLogs(null);
        if (logsOpen) {
          const response = await getTodoLogs(todo.id, {
            headers: unlockToken ? { "X-Meeting-Unlock-Token": unlockToken } : undefined,
          });
          setLogs(response.items);
        }
      }
    } finally {
      setStatusUpdating(false);
    }
  }

  return (
    <Card className={`todo-item todo-card todo-card-${todo.status}`}>
      <div className="todo-card-header">
        <button
          type="button"
          className={`todo-check todo-check-${todo.status}`}
          onClick={() =>
            void changeStatus(todo.status === "done" ? "pending" : "done")
          }
          aria-label="toggle todo status"
          disabled={todo.status === "cancelled" || statusUpdating}
        >
          {todo.status === "done" ? "✓" : ""}
        </button>
        <div className="todo-card-badges">
          <span className={`todo-status-badge todo-status-${todo.status}`}>
            {TODO_STATUS_LABELS[todo.status]}
          </span>
          <span className={`todo-priority-badge todo-priority-${todo.priority}`}>
            {TODO_PRIORITY_LABELS[todo.priority]}
          </span>
          {!compact && meetingTitle ? (
            <span className="todo-meeting-badge">{meetingTitle}</span>
          ) : null}
        </div>
      </div>

      <div className="todo-card-body">
        {editing ? (
          <div className="space-y-3">
            <textarea
              className="input-shell min-h-[88px]"
              value={content}
              onChange={(event) => setContent(event.target.value)}
            />
            <div className="grid gap-3 md:grid-cols-3">
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
                onChange={(event) =>
                  setPriority(event.target.value as TodoItem["priority"])
                }
              >
                <option value="high">高优先级</option>
                <option value="medium">中优先级</option>
                <option value="low">低优先级</option>
              </select>
            </div>
          </div>
        ) : (
          <>
            <div
              className={`todo-main-text ${
                todo.status === "done" ? "todo-main-text-done" : ""
              }`}
            >
              {todo.content}
            </div>
            <div className="todo-card-meta">
              <span>负责人：{todo.assignee || "未指定"}</span>
              <span>截止：{todo.due_date ? todo.due_date.slice(0, 10) : "未指定"}</span>
            </div>
          </>
        )}
      </div>

      <div className="todo-card-actions">
        {editing ? (
          <>
            <button
              className="secondary-button"
              type="button"
              onClick={() => setEditing(false)}
            >
              取消
            </button>
            <button
              className="primary-button"
              type="button"
              onClick={() => void saveEdits()}
            >
              保存
            </button>
          </>
        ) : (
          <>
            <button
              className="secondary-button"
              type="button"
              onClick={() => setEditing(true)}
            >
              编辑
            </button>
            {todo.status === "pending" ? (
              <button
                className="primary-button"
                type="button"
                onClick={() => void changeStatus("done")}
                disabled={statusUpdating}
              >
                {statusUpdating ? "确认中..." : "确认完成"}
              </button>
            ) : null}
            {todo.status !== "cancelled" ? (
              <button
                className="tertiary-button"
                type="button"
                onClick={() => void changeStatus("cancelled")}
                disabled={statusUpdating}
              >
                取消待办
              </button>
            ) : (
              <button
                className="tertiary-button"
                type="button"
                onClick={() => void changeStatus("pending")}
                disabled={statusUpdating}
              >
                恢复待办
              </button>
            )}
            <button
              className="secondary-button"
              type="button"
              onClick={() => void toggleLogs()}
            >
              {logsOpen ? "收起日志" : "查看日志"}
            </button>
          </>
        )}
      </div>

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
    </Card>
  );
}
