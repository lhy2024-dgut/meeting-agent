from datetime import datetime

from sqlalchemy import create_engine

import config
from db.models import Base
from db.repository import MeetingRepository
from services.todo_service import TodoService


def _build_repo(tmp_path) -> MeetingRepository:
    db_url = f"sqlite:///{tmp_path / 'repo_defaults.db'}"
    repo = MeetingRepository(db_url=db_url)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return repo


def test_create_meeting_without_user_assigns_default_admin(tmp_path):
    repo = _build_repo(tmp_path)

    meeting_id = repo.create_meeting(
        "Admin Meeting",
        "admin.wav",
        "short",
        "quiet",
        "hash-admin",
    )
    admin = repo.get_user_by_username(config.DEFAULT_ADMIN_USERNAME)
    assert admin is not None

    meeting = repo.get_meeting_by_id(meeting_id, user_id=admin.id)
    assert meeting is not None
    assert meeting.user_id == admin.id


def test_meeting_uses_the_supplied_meeting_time_for_history_and_stats(tmp_path):
    repo = _build_repo(tmp_path)
    user = repo.create_user("alice", "alice@example.com", "hash", "Alice")
    meeting_time = datetime(2025, 12, 15, 9, 30)
    meeting_id = repo.create_meeting(
        "Past Meeting",
        "past.wav",
        "medium",
        "multi_speaker",
        "hash-past",
        user_id=user.id,
        created_at=meeting_time,
    )

    meeting = repo.get_meeting_by_id(meeting_id, user_id=user.id)
    assert meeting.created_at == meeting_time

    stats = repo.get_stats_overview_data(user_id=user.id)
    assert stats["multi_speaker_meetings"] == 1
    assert stats["monthly_trend"] == [{"month": "2025-12", "count": 1}]


def test_stats_include_todo_closure_metrics(tmp_path):
    repo = _build_repo(tmp_path)
    user = repo.create_user("alice", "alice@example.com", "hash", "Alice")
    meeting_id = repo.create_meeting(
        "Todo Stats",
        "todo.wav",
        "short",
        "unknown",
        "hash-todo",
        user_id=user.id,
    )
    service = TodoService(repo)
    completed = service.create_todo(user.id, meeting_id, content="已完成", assignee="Alice")
    service.update_status(user.id, completed.id, to_status="done")
    service.create_todo(
        user.id,
        meeting_id,
        content="逾期任务",
        assignee="Bob",
        due_date="2020-01-01",
    )

    stats = repo.get_stats_overview_data(user_id=user.id)

    assert stats["total_todos"] == 2
    assert stats["completed_todos"] == 1
    assert stats["overdue_todos"] == 1
    assert stats["todo_assignee_distribution"] == [
        {"key": "Alice", "count": 1},
        {"key": "Bob", "count": 1},
    ]
