from datetime import datetime

from pydantic import BaseModel


class TodoItemResponse(BaseModel):
    id: int
    user_id: int
    meeting_id: int
    content: str
    assignee: str | None = None
    due_date: datetime | None = None
    status: str
    priority: str
    source: str
    is_user_modified: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TodoStatusLogResponse(BaseModel):
    id: int
    todo_id: int
    from_status: str | None = None
    to_status: str
    changed_by: str
    changed_at: datetime | None = None
    reason: str | None = None


class TodoListResponse(BaseModel):
    items: list[TodoItemResponse]


class TodoCreateRequest(BaseModel):
    content: str
    assignee: str | None = None
    due_date: str | None = None
    priority: str = "medium"


class TodoUpdateRequest(BaseModel):
    content: str | None = None
    assignee: str | None = None
    due_date: str | None = None
    priority: str | None = None


class TodoStatusUpdateRequest(BaseModel):
    status: str
    reason: str | None = None


class TodoStatusLogsResponse(BaseModel):
    items: list[TodoStatusLogResponse]
