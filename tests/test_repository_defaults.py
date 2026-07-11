from sqlalchemy import create_engine

import config
from db.models import Base
from db.repository import MeetingRepository


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
