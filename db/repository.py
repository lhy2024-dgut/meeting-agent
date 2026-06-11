from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from db.engine import get_engine, get_session_factory
from db.models import Meeting, Transcription
from logger import get_logger

logger = get_logger(__name__)


class MeetingRepository:
    """会议数据仓库，支持依赖注入覆盖数据库连接。"""

    def __init__(self, db_url=None):
        self.engine = get_engine(url=db_url) if db_url else get_engine()
        self.Session = get_session_factory(engine=self.engine)

    @contextmanager
    def _write_session(self):
        """写事务：成功提交，失败回滚。"""
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
        """只读会话：不提交，用完即关。"""
        session = self.Session()
        try:
            yield session
        finally:
            session.close()

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

    def update_meeting_results(
        self,
        meeting_id,
        minutes,
        action_items,
        resolutions,
        short_summary=None,
        project_name=None,
    ):
        with self._write_session() as session:
            meeting = session.query(Meeting).filter_by(id=meeting_id).first()
            if meeting:
                meeting.minutes_text = minutes
                meeting.action_items_text = action_items
                meeting.resolutions_text = resolutions
                if short_summary is not None:
                    meeting.short_summary = short_summary
                if project_name is not None:
                    meeting.project_name = project_name
                meeting.updated_at = datetime.now()

    def update_meeting_project_name(self, meeting_id, project_name):
        """供前端单字段编辑。"""
        with self._write_session() as session:
            meeting = session.query(Meeting).filter_by(id=meeting_id).first()
            if meeting:
                meeting.project_name = project_name[:255]
                meeting.updated_at = datetime.now()
                return True
            return False

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
                    "summary": text_content,
                    "audio_segment": seg.get("audio_segment", ""),
                }
            )
        with self._write_session() as session:
            session.bulk_insert_mappings(Transcription, mappings)

    def replace_transcriptions(self, meeting_id, segments):
        """Replace all stored transcription segments for a meeting."""
        with self._write_session() as session:
            session.query(Transcription).filter_by(meeting_id=meeting_id).delete()
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
                        "summary": text_content,
                        "audio_segment": seg.get("audio_segment", ""),
                    }
                )
            session.bulk_insert_mappings(Transcription, mappings)

    def delete_meeting(self, meeting_id):
        with self._write_session() as session:
            meeting = session.query(Meeting).filter_by(id=meeting_id).first()
            if meeting:
                session.delete(meeting)
                return True
            return False

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

    def get_all_meetings_safe(self):
        """兼容旧数据库（无 short_summary/project_name 列）的查询。"""
        from sqlalchemy import inspect, text

        with self._read_session() as session:
            inspector = inspect(session.get_bind())
            cols = [col["name"] for col in inspector.get_columns("meetings")]
            has_new_cols = "short_summary" in cols

            if has_new_cols:
                return (
                    session.query(Meeting)
                    .options(joinedload(Meeting.transcriptions))
                    .order_by(Meeting.created_at.desc())
                    .all()
                )

            rows = session.execute(
                text(
                    "SELECT id, title, created_at, updated_at, audio_path, "
                    "duration_category, environment, file_hash, "
                    "minutes_text, action_items_text, resolutions_text "
                    "FROM meetings ORDER BY created_at DESC"
                )
            ).fetchall()
            meetings = []
            for row in rows:
                meeting = Meeting(
                    id=row.id,
                    title=row.title,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    audio_path=row.audio_path,
                    duration_category=row.duration_category,
                    environment=row.environment,
                    file_hash=row.file_hash,
                    minutes_text=row.minutes_text,
                    action_items_text=row.action_items_text,
                    resolutions_text=row.resolutions_text,
                )
                meetings.append(meeting)
            return meetings

    def get_meetings_paginated(self, page=0, page_size=10, search="", dur_filter=None, env_filter=None):
        """分页查询会议列表，不加载 transcriptions。"""
        with self._read_session() as session:
            query = session.query(Meeting)

            if search:
                query = query.filter(
                    or_(
                        Meeting.title.ilike(f"%{search}%"),
                        Meeting.short_summary.ilike(f"%{search}%"),
                        Meeting.project_name.ilike(f"%{search}%"),
                    )
                )
            if dur_filter and dur_filter != "全部":
                mapping = {
                    "短会 (<5min)": "short",
                    "中等 (5-30min)": "medium",
                    "长会 (>30min)": "long",
                }
                value = mapping.get(dur_filter)
                if value:
                    query = query.filter(Meeting.duration_category == value)
            if env_filter and env_filter != "全部":
                mapping = {"安静": "quiet", "嘈杂": "noisy", "多人": "multi_speaker"}
                value = mapping.get(env_filter)
                if value:
                    query = query.filter(Meeting.environment == value)

            total = query.count()
            meetings = (
                query.order_by(Meeting.created_at.desc())
                .offset(page * page_size)
                .limit(page_size)
                .all()
            )
            return meetings, total

    def get_meeting_by_id(self, meeting_id):
        with self._read_session() as session:
            return (
                session.query(Meeting)
                .options(joinedload(Meeting.transcriptions))
                .filter_by(id=meeting_id)
                .first()
            )
