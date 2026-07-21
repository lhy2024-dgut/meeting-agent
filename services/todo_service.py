from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import re

from sqlalchemy.orm import selectinload

from db.models import Meeting, TodoItem, TodoStatusLog

TODO_STATUS_PENDING = "pending"
TODO_STATUS_DONE = "done"
TODO_STATUS_CANCELLED = "cancelled"
TODO_SOURCE_MANUAL = "manual"
TODO_SOURCE_MEETING_PIPELINE = "meeting_pipeline"
_UNSET = object()
TODO_PRIORITIES = {"high", "medium", "low"}
TODO_STATUSES = {TODO_STATUS_PENDING, TODO_STATUS_DONE, TODO_STATUS_CANCELLED}
ALLOWED_STATUS_TRANSITIONS = {
    TODO_STATUS_PENDING: {TODO_STATUS_DONE, TODO_STATUS_CANCELLED},
    TODO_STATUS_DONE: {TODO_STATUS_PENDING},
    TODO_STATUS_CANCELLED: {TODO_STATUS_PENDING},
}


def normalize_priority(priority: str | None) -> str:
    value = (priority or "medium").strip().lower()
    if value not in TODO_PRIORITIES:
        return "medium"
    return value


def normalize_status(status: str | None) -> str:
    value = (status or TODO_STATUS_PENDING).strip().lower()
    if value not in TODO_STATUSES:
        return TODO_STATUS_PENDING
    return value


def parse_due_date(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _split_meta(item: str) -> tuple[str, str | None, datetime | None]:
    parts = [part.strip() for part in item.split("|")]
    content = parts[0].strip()
    assignee = None
    due_date = None

    for meta in parts[1:]:
        normalized = meta.replace("：", ":").strip()
        lowered = normalized.lower()
        if normalized.startswith("负责人:"):
            assignee = normalized.split(":", 1)[-1].strip() or None
            continue
        if normalized.startswith("截止:") or lowered.startswith("due:"):
            raw_due = normalized.split(":", 1)[-1].strip()
            if raw_due:
                try:
                    due_date = parse_due_date(raw_due)
                except ValueError:
                    due_date = None
            continue
        if assignee is None and re.search(r"[A-Za-z\u4e00-\u9fff]", meta):
            assignee = meta
            continue
        if due_date is None:
            try:
                due_date = parse_due_date(meta)
            except ValueError:
                pass

    return content, assignee, due_date


def parse_action_items_text(action_items_text: str | None) -> list[dict[str, object]]:
    if not action_items_text:
        return []

    items: list[dict[str, object]] = []
    for raw_line in action_items_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        cleaned = re.sub(r"^[-*]\s*(\[[ xX]\]\s*)?", "", line).strip()
        cleaned = re.sub(r"^\d+[\.)、]\s*", "", cleaned).strip()
        cleaned = cleaned.lstrip("•").strip()
        if not cleaned:
            continue
        content, assignee, due_date = _split_meta(cleaned)
        if not content:
            continue
        items.append(
            {
                "content": content,
                "assignee": assignee,
                "due_date": due_date,
                "priority": "medium",
            }
        )
    return items


def _content_key(content: str) -> str:
    return " ".join((content or "").split()).casefold()


class TodoTransitionError(ValueError):
    pass


class TodoService:
    def __init__(self, repo):
        self.repo = repo

    @contextmanager
    def _write_session(self):
        session = self.repo.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def _read_session(self):
        session = self.repo.Session()
        try:
            yield session
        finally:
            session.close()

    @staticmethod
    def _apply_user_filter(query, column, user_id: int):
        return query.filter(column == user_id)

    def list_todos(
        self,
        user_id: int,
        *,
        meeting_id: int | None = None,
        status: str | None = None,
        priority: str | None = None,
        include_cancelled: bool = True,
    ) -> list[TodoItem]:
        with self._read_session() as session:
            query = (
                session.query(TodoItem)
                .options(selectinload(TodoItem.status_logs))
            )
            query = self._apply_user_filter(query, TodoItem.user_id, user_id)
            if meeting_id is not None:
                query = query.filter(TodoItem.meeting_id == meeting_id)
            if status:
                query = query.filter(TodoItem.status == normalize_status(status))
            elif not include_cancelled:
                query = query.filter(TodoItem.status != TODO_STATUS_CANCELLED)
            if priority:
                query = query.filter(TodoItem.priority == normalize_priority(priority))
            if meeting_id is not None:
                return query.order_by(TodoItem.id.asc()).all()
            return query.order_by(TodoItem.updated_at.desc(), TodoItem.id.desc()).all()

    def get_todo(self, user_id: int, todo_id: int) -> TodoItem | None:
        with self._read_session() as session:
            query = (
                session.query(TodoItem)
                .options(selectinload(TodoItem.status_logs))
                .filter(TodoItem.id == todo_id)
            )
            query = self._apply_user_filter(query, TodoItem.user_id, user_id)
            return query.first()

    def create_todo(
        self,
        user_id: int,
        meeting_id: int,
        *,
        content: str,
        assignee: str | None = None,
        due_date: str | datetime | None = None,
        priority: str | None = None,
    ) -> TodoItem:
        normalized_content = (content or "").strip()
        if not normalized_content:
            raise TodoTransitionError("Todo content is required")

        with self._write_session() as session:
            meeting_query = session.query(Meeting).filter(Meeting.id == meeting_id)
            meeting_query = self._apply_user_filter(meeting_query, Meeting.user_id, user_id)
            meeting = meeting_query.first()
            if not meeting:
                raise TodoTransitionError("Meeting not found")

            now = datetime.now()
            todo = TodoItem(
                user_id=user_id,
                meeting_id=meeting_id,
                content=normalized_content,
                assignee=(assignee or "").strip() or None,
                due_date=parse_due_date(due_date),
                status=TODO_STATUS_PENDING,
                priority=normalize_priority(priority),
                source=TODO_SOURCE_MANUAL,
                is_user_modified=True,
                created_at=now,
                updated_at=now,
            )
            session.add(todo)
            session.flush()
            session.add(
                TodoStatusLog(
                    todo_id=todo.id,
                    from_status=None,
                    to_status=TODO_STATUS_PENDING,
                    changed_by=f"user:{user_id}",
                    changed_at=now,
                    reason="created",
                )
            )
            session.flush()
            session.refresh(todo)
            return todo

    def update_todo(
        self,
        user_id: int,
        todo_id: int,
        *,
        content: str | None = None,
        assignee: str | None | object = _UNSET,
        due_date: str | datetime | None | object = _UNSET,
        priority: str | None = None,
    ) -> TodoItem:
        with self._write_session() as session:
            todo_query = session.query(TodoItem).filter(TodoItem.id == todo_id)
            todo_query = self._apply_user_filter(todo_query, TodoItem.user_id, user_id)
            todo = todo_query.first()
            if not todo:
                raise TodoTransitionError("Todo not found")

            if content is not None:
                normalized_content = content.strip()
                if not normalized_content:
                    raise TodoTransitionError("Todo content is required")
                todo.content = normalized_content
            if assignee is not _UNSET:
                todo.assignee = (assignee or "").strip() or None
            if due_date is not _UNSET:
                todo.due_date = parse_due_date(due_date)
            if priority is not None:
                todo.priority = normalize_priority(priority)
            if (
                content is not None
                or assignee is not _UNSET
                or due_date is not _UNSET
                or priority is not None
            ):
                todo.is_user_modified = True
            todo.updated_at = datetime.now()
            session.flush()
            session.refresh(todo)
            return todo

    def update_status(
        self,
        user_id: int,
        todo_id: int,
        *,
        to_status: str,
        reason: str | None = None,
    ) -> TodoItem:
        next_status = normalize_status(to_status)
        with self._write_session() as session:
            todo_query = session.query(TodoItem).filter(TodoItem.id == todo_id)
            todo_query = self._apply_user_filter(todo_query, TodoItem.user_id, user_id)
            todo = todo_query.first()
            if not todo:
                raise TodoTransitionError("Todo not found")

            current_status = normalize_status(todo.status)
            if current_status == next_status:
                return todo
            if next_status not in ALLOWED_STATUS_TRANSITIONS.get(current_status, set()):
                raise TodoTransitionError(
                    f"Illegal todo transition: {current_status} -> {next_status}"
                )

            now = datetime.now()
            todo.status = next_status
            todo.is_user_modified = True
            todo.updated_at = now
            session.add(
                TodoStatusLog(
                    todo_id=todo.id,
                    from_status=current_status,
                    to_status=next_status,
                    changed_by=f"user:{user_id}",
                    changed_at=now,
                    reason=reason,
                )
            )
            session.flush()
            session.refresh(todo)
            return todo

    def get_status_logs(self, user_id: int, todo_id: int) -> list[TodoStatusLog]:
        todo = self.get_todo(user_id, todo_id)
        if not todo:
            raise TodoTransitionError("Todo not found")
        return sorted(
            todo.status_logs,
            key=lambda item: item.changed_at or datetime.min,
            reverse=True,
        )

    def sync_meeting_todos(
        self,
        user_id: int,
        meeting_id: int,
        action_items_text: str | None,
        *,
        replace: bool = False,
    ) -> list[TodoItem]:
        parsed_items = parse_action_items_text(action_items_text)
        with self._write_session() as session:
            meeting_query = session.query(Meeting).filter(Meeting.id == meeting_id)
            meeting_query = self._apply_user_filter(meeting_query, Meeting.user_id, user_id)
            meeting = meeting_query.first()
            if not meeting:
                raise TodoTransitionError("Meeting not found")

            existing_query = session.query(TodoItem).filter(TodoItem.meeting_id == meeting_id)
            existing_query = self._apply_user_filter(existing_query, TodoItem.user_id, user_id)
            existing = existing_query.order_by(TodoItem.id.asc()).all()
            if existing and not replace:
                return existing

            protected_items = [
                item
                for item in existing
                if item.source != TODO_SOURCE_MEETING_PIPELINE or item.is_user_modified
            ]
            protected_content_keys = {_content_key(item.content) for item in protected_items}

            if replace:
                replaceable_ids = [
                    item.id
                    for item in existing
                    if item.source == TODO_SOURCE_MEETING_PIPELINE
                    and not item.is_user_modified
                ]
                if replaceable_ids:
                    session.query(TodoStatusLog).filter(
                        TodoStatusLog.todo_id.in_(replaceable_ids)
                    ).delete(synchronize_session=False)
                    session.query(TodoItem).filter(
                        TodoItem.id.in_(replaceable_ids)
                    ).delete(synchronize_session=False)

            if not parsed_items:
                session.flush()
                return protected_items

            now = datetime.now()
            created: list[TodoItem] = []
            for item in parsed_items:
                content = str(item["content"]).strip()
                if _content_key(content) in protected_content_keys:
                    continue
                todo = TodoItem(
                    user_id=user_id,
                    meeting_id=meeting_id,
                    content=content,
                    assignee=item.get("assignee"),
                    due_date=item.get("due_date"),
                    status=TODO_STATUS_PENDING,
                    priority=normalize_priority(str(item.get("priority", "medium"))),
                    source=TODO_SOURCE_MEETING_PIPELINE,
                    is_user_modified=False,
                    created_at=now,
                    updated_at=now,
                )
                session.add(todo)
                session.flush()
                session.add(
                    TodoStatusLog(
                        todo_id=todo.id,
                        from_status=None,
                        to_status=TODO_STATUS_PENDING,
                        changed_by="meeting_pipeline",
                        changed_at=now,
                        reason="parsed from action items",
                    )
                )
                created.append(todo)

            session.flush()
            return protected_items + created
