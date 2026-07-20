from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from api.deps import get_meeting_repository
from api.routers import meetings
from db.models import Base
from db.repository import MeetingRepository
from services.auth_service import hash_password


def _build_repo(tmp_path) -> MeetingRepository:
    db_url = f"sqlite:///{tmp_path / 'single_account.db'}"
    repo = MeetingRepository(db_url=db_url)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return repo


def test_meeting_list_is_global_and_unprotected_in_single_account_mode(tmp_path):
    repo = _build_repo(tmp_path)
    user_a = repo.create_user("alice", "alice@example.com", hash_password("StrongPass1"), "Alice")
    user_b = repo.create_user("bob", "bob@example.com", hash_password("StrongPass2"), "Bob")
    repo.create_meeting("Alice Meeting", "a.wav", "short", "quiet", "hash-a", user_id=user_a.id)
    repo.create_meeting("Bob Meeting", "b.wav", "medium", "noisy", "hash-b", user_id=user_b.id)

    app = FastAPI()
    app.include_router(meetings.router)
    app.dependency_overrides[get_meeting_repository] = lambda: repo
    client = TestClient(app)

    response = client.get("/api/meetings")

    assert response.status_code == 200
    assert {item["title"] for item in response.json()["items"]} == {
        "Alice Meeting",
        "Bob Meeting",
    }
