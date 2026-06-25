from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user, get_meeting_repository
from api.schemas.todos import (
    TodoCreateRequest,
    TodoItemResponse,
    TodoListResponse,
    TodoStatusLogsResponse,
    TodoStatusLogResponse,
    TodoStatusUpdateRequest,
    TodoUpdateRequest,
)
from db.repository import MeetingRepository
from services.todo_service import TodoService, TodoTransitionError

router = APIRouter(prefix="/api", tags=["todos"])


def _serialize_todo(todo) -> TodoItemResponse:
    return TodoItemResponse(
        id=todo.id,
        user_id=todo.user_id,
        meeting_id=todo.meeting_id,
        content=todo.content,
        assignee=todo.assignee,
        due_date=todo.due_date,
        status=todo.status,
        priority=todo.priority,
        created_at=todo.created_at,
        updated_at=todo.updated_at,
    )


def _serialize_log(item) -> TodoStatusLogResponse:
    return TodoStatusLogResponse(
        id=item.id,
        todo_id=item.todo_id,
        from_status=item.from_status,
        to_status=item.to_status,
        changed_by=item.changed_by,
        changed_at=item.changed_at,
        reason=item.reason,
    )


def _get_service(repo: MeetingRepository) -> TodoService:
    return TodoService(repo)


@router.get("/todos", response_model=TodoListResponse)
def list_todos(
    meeting_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    include_cancelled: bool = Query(default=True),
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> TodoListResponse:
    service = _get_service(repo)
    items = service.list_todos(
        current_user.id,
        meeting_id=meeting_id,
        status=status,
        priority=priority,
        include_cancelled=include_cancelled,
    )
    return TodoListResponse(items=[_serialize_todo(item) for item in items])


@router.post("/meetings/{meeting_id}/todos", response_model=TodoItemResponse)
def create_meeting_todo(
    meeting_id: int,
    payload: TodoCreateRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> TodoItemResponse:
    service = _get_service(repo)
    try:
        todo = service.create_todo(
            current_user.id,
            meeting_id,
            content=payload.content,
            assignee=payload.assignee,
            due_date=payload.due_date,
            priority=payload.priority,
        )
    except TodoTransitionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_todo(todo)


@router.patch("/todos/{todo_id}", response_model=TodoItemResponse)
def update_todo(
    todo_id: int,
    payload: TodoUpdateRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> TodoItemResponse:
    service = _get_service(repo)
    try:
        todo = service.update_todo(
            current_user.id,
            todo_id,
            content=payload.content,
            assignee=payload.assignee,
            due_date=payload.due_date,
            priority=payload.priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TodoTransitionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize_todo(todo)


@router.post("/todos/{todo_id}/status", response_model=TodoItemResponse)
def update_todo_status(
    todo_id: int,
    payload: TodoStatusUpdateRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> TodoItemResponse:
    service = _get_service(repo)
    try:
        todo = service.update_status(
            current_user.id,
            todo_id,
            to_status=payload.status,
            changed_by=payload.changed_by,
            reason=payload.reason,
        )
    except TodoTransitionError as exc:
        detail = str(exc)
        status_code = 400 if "Illegal todo transition" in detail else 404
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return _serialize_todo(todo)


@router.get("/todos/{todo_id}/logs", response_model=TodoStatusLogsResponse)
def get_todo_logs(
    todo_id: int,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> TodoStatusLogsResponse:
    service = _get_service(repo)
    try:
        logs = service.get_status_logs(current_user.id, todo_id)
    except TodoTransitionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TodoStatusLogsResponse(items=[_serialize_log(item) for item in logs])
