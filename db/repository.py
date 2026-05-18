from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy.pool import QueuePool

import config
from db.models import Base, Meeting, Transcription


class MeetingRepository:
    def __init__(self):
        self.engine = create_engine(
            config.DATABASE_URL,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[OK] 数据库已连接:", config.DATABASE_URL)

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    @contextmanager
    def session_scope(self):
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_meeting(
        self, title, audio_path, duration_category, environment, file_hash=""
    ):
        with self.session_scope() as session:
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
        with self.session_scope() as session:
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
            mappings.append(
                {
                    "meeting_id": meeting_id,
                    "text": text_content,
                    "timestamp": seg.get("timestamp", 0.0),
                    "start_time": seg.get("start", 0.0),
                    "end_time": seg.get("end", 0.0),
                    "summary": (
                        text_content[:120] + "..."
                        if len(text_content) > 120
                        else text_content
                    ),
                    "audio_segment": seg.get("audio_segment", ""),
                }
            )
        with self.session_scope() as session:
            session.bulk_insert_mappings(Transcription, mappings)

    def get_meeting_by_hash(self, file_hash):
        if not file_hash:
            return None
        with self.session_scope() as session:
            return (
                session.query(Meeting)
                .options(joinedload(Meeting.transcriptions))
                .filter_by(file_hash=file_hash)
                .first()
            )

    def get_all_meetings(self):
        with self.session_scope() as session:
            return (
                session.query(Meeting)
                .options(joinedload(Meeting.transcriptions))
                .order_by(Meeting.created_at.desc())
                .all()
            )

    def get_meeting_by_id(self, meeting_id):
        with self.session_scope() as session:
            return (
                session.query(Meeting)
                .options(joinedload(Meeting.transcriptions))
                .filter_by(id=meeting_id)
                .first()
            )
