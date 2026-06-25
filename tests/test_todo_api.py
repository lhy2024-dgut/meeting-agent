from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from api.deps import get_current_user, get_meeting_repository
from api.routers import meetings, todos
from db.models import Base
from db.repository import MeetingRepository
from services.auth_service import hash_password


def _build_repo(tmp_path) -> MeetingRepository:
    db_url = f"sqlite:///{tmp_path / 'todos.db'}"
    repo = MeetingRepository(db_url=db_url)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return repo


def test_todo_crud_and_logs(tmp_path):
    repo = _build_repo(tmp_path)
    user = repo.create_user("alice", "alice@example.com", hash_password("StrongPass1"), "Alice")
    meeting_id = repo.create_meeting("Alice Meeting", "a.wav", "short", "quiet", "hash-a", user_id=user.id)

    app = FastAPI()
    app.include_router(meetings.router)
    app.include_router(todos.router)
    app.dependency_overrides[get_meeting_repository] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user.id, username=user.username)
    client = TestClient(app)

    created = client.post(
        f"/api/meetings/{meeting_id}/todos",
        json={
            "content": "准备发布说明",
            "assignee": "Alice",
            "priority": "high",
        },
    )
    assert created.status_code == 200
    todo = created.json()
    assert todo["status"] == "pending"
    assert todo["priority"] == "high"

    listed = client.get(f"/api/todos?meeting_id={meeting_id}")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    updated = client.patch(
        f"/api/todos/{todo['id']}",
        json={
            "assignee": "Alice Owner",
            "priority": "low",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["assignee"] == "Alice Owner"
    assert updated.json()["priority"] == "low"

    status_updated = client.post(
        f"/api/todos/{todo['id']}/status",
        json={"status": "done", "changed_by": "manual", "reason": "已处理"},
    )
    assert status_updated.status_code == 200
    assert status_updated.json()["status"] == "done"

    logs = client.get(f"/api/todos/{todo['id']}/logs")
    assert logs.status_code == 200
    assert len(logs.json()["items"]) == 2


def test_meeting_detail_returns_synced_todos(tmp_path):
    repo = _build_repo(tmp_path)
    user = repo.create_user("alice", "alice@example.com", hash_password("StrongPass1"), "Alice")
    meeting_id = repo.create_meeting("Sync Meeting", "a.wav", "short", "quiet", "hash-a", user_id=user.id)
    repo.update_meeting_results(
        meeting_id,
        "minutes",
        "- 准备预算评审 | Alice\n- 提交测试报告 | Bob",
        "resolution",
        user_id=user.id,
    )

    app = FastAPI()
    app.include_router(meetings.router)
    app.include_router(todos.router)
    app.dependency_overrides[get_meeting_repository] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user.id, username=user.username)
    client = TestClient(app)

    detail = client.get(f"/api/meetings/{meeting_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["action_item_count"] == 2
    assert [item["content"] for item in body["todos"]] == ["准备预算评审", "提交测试报告"]
