from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from api.deps import get_current_user, get_meeting_repository
from api.routers import chat
from api.services.chat_session_manager import ChatSession, ChatSessionManager
from api.services.chat_session_manager import chat_session_manager
from db.models import Base
from db.repository import MeetingRepository
from services.auth_service import hash_password


def _build_repo(tmp_path) -> MeetingRepository:
    db_url = f"sqlite:///{tmp_path / 'chat_isolation.db'}"
    repo = MeetingRepository(db_url=db_url)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return repo


def test_chat_session_cannot_be_used_by_another_user(tmp_path):
    repo = _build_repo(tmp_path)
    alice = repo.create_user("alice", "alice@example.com", hash_password("StrongPass1"), "Alice")
    bob = repo.create_user("bob", "bob@example.com", hash_password("StrongPass2"), "Bob")
    meeting_id = repo.create_meeting(
        "Alice Meeting",
        "alice.wav",
        "short",
        "quiet",
        "hash-a",
        user_id=alice.id,
    )

    app = FastAPI()
    app.include_router(chat.router)
    app.dependency_overrides[get_meeting_repository] = lambda: repo
    current_user = {"value": SimpleNamespace(id=alice.id, username=alice.username)}
    app.dependency_overrides[get_current_user] = lambda: current_user["value"]
    client = TestClient(app)

    created = client.post(
        "/api/chat/sessions",
        json={"mode": "single", "meeting_id": meeting_id},
    )
    assert created.status_code == 200

    current_user["value"] = SimpleNamespace(id=bob.id, username=bob.username)
    response = client.post(
        f"/api/chat/sessions/{created.json()['session_id']}/messages",
        json={"message": "Show Alice's meeting details"},
    )
    assert response.status_code == 403


def test_chat_session_manager_removes_expired_sessions():
    manager = ChatSessionManager()
    manager._sessions["expired"] = ChatSession(
        session_id="expired",
        user_id=1,
        mode="single",
        meeting_id=1,
        agent=None,
        last_accessed_at=0,
    )

    assert manager.get_session("expired") is None
    assert "expired" not in manager._sessions
