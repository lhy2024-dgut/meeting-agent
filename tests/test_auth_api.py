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


def test_register_login_refresh_and_me(tmp_path):
    repo = _build_repo(tmp_path)
    app = FastAPI()
    app.include_router(auth.router)
    app.dependency_overrides[get_meeting_repository] = lambda: repo
    client = TestClient(app)

    registered = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "StrongPass1",
            "display_name": "Alice",
        },
    )
    assert registered.status_code == 201
    assert registered.json()["username"] == "alice"

    login = client.post(
        "/api/auth/login",
        json={"login": "alice", "password": "StrongPass1"},
    )
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"

    refreshed = client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]


def test_me_accepts_access_token_cookie(tmp_path):
    repo = _build_repo(tmp_path)
    app = FastAPI()
    app.include_router(auth.router)
    app.dependency_overrides[get_meeting_repository] = lambda: repo
    client = TestClient(app)

    client.post(
        "/api/auth/register",
        json={
            "username": "cookie-user",
            "email": "cookie@example.com",
            "password": "StrongPass1",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"login": "cookie-user", "password": "StrongPass1"},
    )
    assert login.status_code == 200
    access_token = login.json()["access_token"]

    client.cookies.set("meeting_agent_access_token", access_token)
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "cookie-user"


def test_register_rejects_duplicates_and_weak_password(tmp_path):
    repo = _build_repo(tmp_path)
    app = FastAPI()
    app.include_router(auth.router)
    app.dependency_overrides[get_meeting_repository] = lambda: repo
    client = TestClient(app)

    first = client.post(
        "/api/auth/register",
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "StrongPass1",
        },
    )
    assert first.status_code == 201

    duplicate = client.post(
        "/api/auth/register",
        json={
            "username": "bob",
            "email": "bob2@example.com",
            "password": "StrongPass1",
        },
    )
    assert duplicate.status_code == 409

    weak = client.post(
        "/api/auth/register",
        json={
            "username": "carol",
            "email": "carol@example.com",
            "password": "weak",
        },
    )
    assert weak.status_code == 400
