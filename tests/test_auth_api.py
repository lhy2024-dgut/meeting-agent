from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from api.deps import get_meeting_repository
from api.routers import auth
from db.models import Base
from db.repository import MeetingRepository


def _build_repo(tmp_path: Path) -> MeetingRepository:
    db_url = f"sqlite:///{tmp_path / 'auth.db'}"
    repo = MeetingRepository(db_url=db_url)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return repo


def _build_client(repo: MeetingRepository) -> TestClient:
    app = FastAPI()
    app.include_router(auth.router)
    app.dependency_overrides[get_meeting_repository] = lambda: repo
    return TestClient(app)


def test_single_account_me_works_without_token(tmp_path):
    repo = _build_repo(tmp_path)
    client = _build_client(repo)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "admin"
    assert body["email"] == "admin@example.com"


def test_single_account_login_and_refresh_return_default_user_tokens(tmp_path):
    repo = _build_repo(tmp_path)
    client = _build_client(repo)

    login = client.post(
        "/api/auth/login",
        json={"login": "anything", "password": "anything"},
    )
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    refreshed = client.post(
        "/api/auth/refresh",
        json={"refresh_token": "stale-or-missing-token"},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]


def test_single_account_disables_registration_and_logout_is_idempotent(tmp_path):
    repo = _build_repo(tmp_path)
    client = _build_client(repo)

    registered = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "StrongPass1",
        },
    )
    assert registered.status_code == 409

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 200
