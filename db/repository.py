from contextlib import contextmanager
from datetime import datetime

from sqlalchemy.orm import joinedload

from db.engine import get_engine, get_session_factory
from db.models import Meeting, Transcription
from logger import get_logger

logger = get_logger(__name__)


class MeetingRepository:
    """会议数据仓库，支持依赖注入覆盖数据库连接"""

    def __init__(self, db_url=None):
        self.engine = get_engine(url=db_url) if db_url else get_engine()
        self.Session = get_session_factory(engine=self.engine)

    @contextmanager
    def _write_session(self):
        """写事务：commit on success, rollback on error"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def _read_session(self):
        """只读会话：不 commit，用完即关"""
        session = self.Session()
        try:
            yield session
        finally:
            session.close()

    # ---- 写操作 ----

    def create_meeting(self, title, audio_path, duration_category, environment, file_hash=""):
        with self._write_session() as session:
            meeting = Meeting(
                title=title,
                audio_path=audio_path,
                duration_category=duration_category,
                environment=environment,
                file_hash=file_hash,
                created_at=datetime.now(),
            )
            session.add(meeting)
            session.flush()
            return meeting.id

    def update_meeting_results(self, meeting_id, minutes, action_items, resolutions):
        with self._write_session() as session:
            meeting = session.query(Meeting).filter_by(id=meeting_id).first()
            if meeting:
                meeting.minutes_text = minutes
                meeting.action_items_text = action_items
                meeting.resolutions_text = resolutions
                meeting.updated_at = datetime.now()

    def add_transcriptions_bulk(self, meeting_id, segments):
        if not segments:
            return
        mappings = []
        for seg in segments:
            text_content = seg.get("text", "")
            mappings.append({
                "meeting_id": meeting_id,
                "text": text_content,
                "timestamp": seg.get("timestamp", 0.0),
                "start_time": seg.get("start", 0.0),
                "end_time": seg.get("end", 0.0),
                "summary": text_content,
                "audio_segment": seg.get("audio_segment", ""),
            })
        with self._write_session() as session:
            session.bulk_insert_mappings(Transcription, mappings)

    def delete_meeting(self, meeting_id):
        with self._write_session() as session:
            meeting = session.query(Meeting).filter_by(id=meeting_id).first()
            if meeting:
                session.delete(meeting)
                return True
            return False

    # ---- 读操作 ----

    def get_meeting_by_hash(self, file_hash):
        if not file_hash:
            return None
        with self._read_session() as session:
            return (
                session.query(Meeting)
                .options(joinedload(Meeting.transcriptions))
                .filter_by(file_hash=file_hash)
                .first()
            )

    def get_all_meetings(self):
        with self._read_session() as session:
            return (
                session.query(Meeting)
                .options(joinedload(Meeting.transcriptions))
                .order_by(Meeting.created_at.desc())
                .all()
            )

    def get_meeting_by_id(self, meeting_id):
        with self._read_session() as session:
            return (
                session.query(Meeting)
                .options(joinedload(Meeting.transcriptions))
                .filter_by(id=meeting_id)
                .first()
            )
