from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from api.deps import get_current_user, get_meeting_repository
from api.routers import chat, contacts, exports, meetings, privacy, todos
from db.models import Base
from db.repository import MeetingRepository
from services.auth_service import hash_password
from services.privacy_service import create_meeting_unlock_token
from services.todo_service import TodoService


def _build_repo(tmp_path) -> MeetingRepository:
    db_url = f"sqlite:///{tmp_path / 'privacy.db'}"
    repo = MeetingRepository(db_url=db_url)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return repo


def _build_client(repo: MeetingRepository, current_user) -> TestClient:
    app = FastAPI()
    app.include_router(privacy.router)
    app.include_router(meetings.router)
    app.include_router(exports.router)
    app.include_router(contacts.router)
    app.include_router(chat.router)
    app.include_router(todos.router)
    app.dependency_overrides[get_meeting_repository] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


def _seed_meetings(repo: MeetingRepository, user_id: int) -> tuple[int, int]:
    public_id = repo.create_meeting(
        "Public Meeting",
        "public.wav",
        "short",
        "quiet",
        "hash-public",
        user_id=user_id,
    )
    private_id = repo.create_meeting(
        "Private Meeting",
        "private.wav",
        "medium",
        "multi_speaker",
        "hash-private",
        is_private=True,
        user_id=user_id,
    )
    repo.update_meeting_results(
        private_id,
        "Sensitive minutes",
        "Sensitive task",
        "Sensitive resolution",
        short_summary="Sensitive summary",
        project_name="Sensitive project",
        user_id=user_id,
    )
    return public_id, private_id


def test_private_meeting_list_is_masked_and_detail_requires_unlock(tmp_path):
    repo = _build_repo(tmp_path)
    user = repo.create_user(
        "alice",
        "alice@example.com",
        hash_password("StrongPass1"),
        "Alice",
    )
    _, private_id = _seed_meetings(repo, user.id)
    client = _build_client(repo, user)

    listed = client.get("/api/meetings?page_size=50")
    assert listed.status_code == 200
    private_summary = next(item for item in listed.json()["items"] if item["id"] == private_id)
    assert private_summary["is_private"] is True
    assert private_summary["short_summary"] == ""
    assert private_summary["project_name"] == ""
    assert private_summary["action_item_count"] == 0
    assert private_summary["resolution_count"] == 0

    assert client.get(f"/api/meetings/{private_id}").status_code == 403
    wrong_password = client.post(
        "/api/privacy/unlock",
        json={"scope": "meeting", "meeting_id": private_id, "password": "wrong"},
    )
    assert wrong_password.status_code == 401

    unlocked = client.post(
        "/api/privacy/unlock",
        json={
            "scope": "meeting",
            "meeting_id": private_id,
            "password": "StrongPass1",
        },
    )
    assert unlocked.status_code == 200
    headers = {"X-Meeting-Unlock-Token": unlocked.json()["unlock_token"]}
    detail = client.get(f"/api/meetings/{private_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["minutes_text"] == "Sensitive minutes"


def test_meeting_unlock_is_bound_to_meeting_and_expiry(tmp_path):
    repo = _build_repo(tmp_path)
    user = repo.create_user(
        "alice",
        "alice@example.com",
        hash_password("StrongPass1"),
        "Alice",
    )
    first_id = repo.create_meeting(
        "First Private",
        "first.wav",
        "short",
        "quiet",
        "hash-first",
        is_private=True,
        user_id=user.id,
    )
    second_id = repo.create_meeting(
        "Second Private",
        "second.wav",
        "short",
        "quiet",
        "hash-second",
        is_private=True,
        user_id=user.id,
    )
    client = _build_client(repo, user)

    token, _ = create_meeting_unlock_token(
        user_id=user.id,
        token_version=user.token_version or 0,
        meeting_id=first_id,
    )
    assert client.get(
        f"/api/meetings/{second_id}",
        headers={"X-Meeting-Unlock-Token": token},
    ).status_code == 403

    expired_token, _ = create_meeting_unlock_token(
        user_id=user.id,
        token_version=user.token_version or 0,
        meeting_id=first_id,
        expires_in_minutes=-1,
    )
    assert client.get(
        f"/api/meetings/{first_id}",
        headers={"X-Meeting-Unlock-Token": expired_token},
    ).status_code == 403


def test_private_content_subroutes_require_meeting_unlock(tmp_path):
    repo = _build_repo(tmp_path)
    user = repo.create_user(
        "alice",
        "alice@example.com",
        hash_password("StrongPass1"),
        "Alice",
    )
    _, private_id = _seed_meetings(repo, user.id)
    client = _build_client(repo, user)

    protected_requests = [
        ("get", f"/api/meetings/{private_id}/transcript"),
        ("get", f"/api/meetings/{private_id}/html-summary"),
        ("get", f"/api/meetings/{private_id}/terms"),
        ("get", f"/api/meetings/{private_id}/exports/download"),
        ("get", f"/api/meetings/{private_id}/email-logs"),
        ("post", f"/api/meetings/{private_id}/html-summary/generate"),
        ("post", f"/api/meetings/{private_id}/regenerate"),
        ("post", f"/api/meetings/{private_id}/exports"),
    ]
    for method, path in protected_requests:
        response = client.request(method, path, json={} if method == "post" else None)
        assert response.status_code == 403, path


def test_cross_chat_scope_freezes_allowed_meeting_ids(tmp_path, monkeypatch):
    repo = _build_repo(tmp_path)
    user = repo.create_user(
        "alice",
        "alice@example.com",
        hash_password("StrongPass1"),
        "Alice",
    )
    public_id, private_id = _seed_meetings(repo, user.id)
    client = _build_client(repo, user)
    captured: list[list[int]] = []

    def fake_create_session(**kwargs):
        captured.append(kwargs["meeting_ids"])
        return SimpleNamespace(
            session_id=f"session-{len(captured)}",
            mode=kwargs["mode"],
            meeting_id=kwargs["meeting_id"],
        )

    monkeypatch.setattr(chat.chat_session_manager, "create_session", fake_create_session)

    public_only = client.post(
        "/api/chat/sessions",
        json={"mode": "cross", "privacy_scope": "public_only"},
    )
    assert public_only.status_code == 200
    assert captured[-1] == [public_id]

    without_unlock = client.post(
        "/api/chat/sessions",
        json={"mode": "cross", "privacy_scope": "all"},
    )
    assert without_unlock.status_code == 403

    unlocked = client.post(
        "/api/privacy/unlock",
        json={"scope": "cross_chat_all", "password": "StrongPass1"},
    )
    assert unlocked.status_code == 200
    all_content = client.post(
        "/api/chat/sessions",
        json={
            "mode": "cross",
            "privacy_scope": "all",
            "unlock_token": unlocked.json()["unlock_token"],
        },
    )
    assert all_content.status_code == 200
    assert set(captured[-1]) == {public_id, private_id}


def test_file_hash_cache_lookup_isolated_by_privacy(tmp_path):
    repo = _build_repo(tmp_path)
    user = repo.create_user("alice", "alice@example.com", "hash", "Alice")
    public_id = repo.create_meeting(
        "Public",
        "same.wav",
        "short",
        "quiet",
        "same-hash",
        is_private=False,
        user_id=user.id,
        created_at=datetime(2026, 1, 1),
    )
    private_id = repo.create_meeting(
        "Private",
        "same.wav",
        "short",
        "quiet",
        "same-hash",
        is_private=True,
        user_id=user.id,
        created_at=datetime(2026, 1, 2),
    )

    assert repo.get_meeting_by_hash(
        "same-hash", user_id=user.id, is_private=False
    ).id == public_id
    assert repo.get_meeting_by_hash(
        "same-hash", user_id=user.id, is_private=True
    ).id == private_id


def test_private_meeting_todos_are_hidden_and_require_unlock(tmp_path):
    repo = _build_repo(tmp_path)
    user = repo.create_user(
        "alice",
        "alice@example.com",
        hash_password("StrongPass1"),
        "Alice",
    )
    public_id, private_id = _seed_meetings(repo, user.id)
    service = TodoService(repo)
    public_todo = service.create_todo(
        user.id, public_id, content="Public todo", assignee="Public Owner"
    )
    private_todo = service.create_todo(
        user.id, private_id, content="Private todo", assignee="Private Owner"
    )
    client = _build_client(repo, user)

    global_list = client.get("/api/todos")
    assert global_list.status_code == 200
    assert [item["id"] for item in global_list.json()["items"]] == [public_todo.id]

    assert client.get(f"/api/todos?meeting_id={private_id}").status_code == 403
    assert client.patch(
        f"/api/todos/{private_todo.id}", json={"content": "Leaked edit"}
    ).status_code == 403

    token, _ = create_meeting_unlock_token(
        user_id=user.id,
        token_version=user.token_version or 0,
        meeting_id=private_id,
    )
    headers = {"X-Meeting-Unlock-Token": token}
    private_list = client.get(f"/api/todos?meeting_id={private_id}", headers=headers)
    assert private_list.status_code == 200
    assert [item["id"] for item in private_list.json()["items"]] == [private_todo.id]

    stats = repo.get_stats_overview_data(user_id=user.id)
    assert stats["total_todos"] == 1
    assert stats["todo_assignee_distribution"] == [
        {"key": "Public Owner", "count": 1}
    ]
