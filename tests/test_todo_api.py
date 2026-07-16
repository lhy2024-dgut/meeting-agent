from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from api.deps import get_current_user, get_meeting_repository
from api.routers import meetings, todos
from db.models import Base
from db.repository import MeetingRepository
from services.auth_service import hash_password
from services.todo_service import TodoService


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

    cleared = client.patch(
        f"/api/todos/{todo['id']}",
        json={"assignee": None, "due_date": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["assignee"] is None
    assert cleared.json()["due_date"] is None

    status_updated = client.post(
        f"/api/todos/{todo['id']}/status",
        json={"status": "done", "changed_by": "meeting_pipeline", "reason": "已处理"},
    )
    assert status_updated.status_code == 200
    assert status_updated.json()["status"] == "done"

    logs = client.get(f"/api/todos/{todo['id']}/logs")
    assert logs.status_code == 200
    assert len(logs.json()["items"]) == 2
    assert logs.json()["items"][0]["changed_by"] == f"user:{user.id}"


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


def test_regeneration_keeps_manual_and_modified_todos_with_their_logs(tmp_path):
    repo = _build_repo(tmp_path)
    user = repo.create_user("alice", "alice@example.com", hash_password("StrongPass1"), "Alice")
    meeting_id = repo.create_meeting("Sync Meeting", "a.wav", "short", "quiet", "hash-a", user_id=user.id)
    service = TodoService(repo)

    initial = service.sync_meeting_todos(
        user.id,
        meeting_id,
        "- 自动任务 A\n- 自动任务 B",
        replace=True,
    )
    automatic_a = next(item for item in initial if item.content == "自动任务 A")
    manual = service.create_todo(user.id, meeting_id, content="人工补充任务")
    service.update_status(user.id, automatic_a.id, to_status="done")

    regenerated = service.sync_meeting_todos(
        user.id,
        meeting_id,
        "- 自动任务 A\n- 自动任务 C",
        replace=True,
    )

    by_content = {item.content: item for item in regenerated}
    assert set(by_content) == {"自动任务 A", "自动任务 C", "人工补充任务"}
    assert by_content["自动任务 A"].status == "done"
    assert by_content["自动任务 A"].is_user_modified is True
    assert by_content["自动任务 C"].source == "meeting_pipeline"
    assert by_content["人工补充任务"].source == "manual"
    assert len(service.get_status_logs(user.id, automatic_a.id)) == 2
    assert len(service.get_status_logs(user.id, manual.id)) == 1
