from sqlalchemy import create_engine

from db.models import Base
from db.repository import MeetingRepository
from services.auth_service import hash_password
from services.todo_service import TodoService, TodoTransitionError


def _build_repo(tmp_path) -> MeetingRepository:
    db_url = f"sqlite:///{tmp_path / 'todos_state.db'}"
    repo = MeetingRepository(db_url=db_url)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return repo


def test_illegal_transition_is_blocked(tmp_path):
    repo = _build_repo(tmp_path)
    user = repo.create_user("alice", "alice@example.com", hash_password("StrongPass1"), "Alice")
    meeting_id = repo.create_meeting("State Meeting", "a.wav", "short", "quiet", "hash-a", user_id=user.id)
    service = TodoService(repo)

    todo = service.create_todo(user.id, meeting_id, content="准备发布", priority="medium")
    done = service.update_status(user.id, todo.id, to_status="done")
    assert done.status == "done"

    try:
      service.update_status(user.id, todo.id, to_status="cancelled")
      raise AssertionError("expected transition error")
    except TodoTransitionError as exc:
      assert "Illegal todo transition" in str(exc)

    reset = service.update_status(user.id, todo.id, to_status="pending")
    assert reset.status == "pending"
