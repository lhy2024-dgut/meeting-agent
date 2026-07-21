from contextlib import contextmanager
from datetime import datetime

import bcrypt
import config
from sqlalchemy import case, func, or_
from sqlalchemy.orm import joinedload

from db.engine import get_engine, get_session_factory
from db.models import Contact, ContactGroup, EmailLog, Meeting, TodoItem, Transcription, User
from logger import get_logger

logger = get_logger(__name__)


def _hash_password(raw_password: str) -> str:
    return bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


class MeetingRepository:
    """会议数据仓库，支持依赖注入覆盖数据库连接。"""

    def __init__(self, db_url=None):
        self.engine = get_engine(url=db_url) if db_url else get_engine()
        self.Session = get_session_factory(engine=self.engine)

    @contextmanager
    def _write_session(self):
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
        session = self.Session()
        try:
            yield session
        finally:
            session.close()

    @staticmethod
    def _apply_user_filter(query, user_id):
        if user_id is None:
            return query
        return query.filter(Meeting.user_id == user_id)

    def _ensure_default_user(self, session) -> User:
        user = session.query(User).filter_by(username=config.DEFAULT_ADMIN_USERNAME).first()
        if user:
            return user

        user = User(
            username=config.DEFAULT_ADMIN_USERNAME,
            email=config.DEFAULT_ADMIN_EMAIL,
            password_hash=_hash_password(config.DEFAULT_ADMIN_PASSWORD),
            display_name=config.DEFAULT_ADMIN_DISPLAY_NAME,
            created_at=datetime.now(),
        )
        session.add(user)
        session.flush()
        return user

    def get_or_create_default_user(self) -> User:
        with self._write_session() as session:
            return self._ensure_default_user(session)

    def create_user(self, username, email, password_hash, display_name=""):
        with self._write_session() as session:
            user = User(
                username=username,
                email=email,
                password_hash=password_hash,
                display_name=display_name or username,
                created_at=datetime.now(),
            )
            session.add(user)
            session.flush()
            return user

    def get_user_by_id(self, user_id):
        with self._read_session() as session:
            return session.query(User).filter_by(id=user_id).first()

    def get_user_by_username(self, username):
        with self._read_session() as session:
            return session.query(User).filter_by(username=username).first()

    def get_user_by_email(self, email):
        with self._read_session() as session:
            return session.query(User).filter_by(email=email).first()

    def get_user_by_login(self, login):
        with self._read_session() as session:
            return (
                session.query(User)
                .filter(or_(User.username == login, User.email == login))
                .first()
            )

    def update_user_last_login(self, user_id):
        with self._write_session() as session:
            user = session.query(User).filter_by(id=user_id).first()
            if user:
                user.last_login_at = datetime.now()

    def update_user_profile(self, user_id, *, display_name):
        with self._write_session() as session:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return None
            user.display_name = (display_name or "").strip() or user.username
            session.flush()
            return user

    def update_user_password(self, user_id, *, password_hash):
        with self._write_session() as session:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return False
            user.password_hash = password_hash
            user.token_version = (user.token_version or 0) + 1
            session.flush()
            return True

    def invalidate_user_tokens(self, user_id):
        with self._write_session() as session:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return False
            user.token_version = (user.token_version or 0) + 1
            session.flush()
            return True

    def update_user_smtp_settings(
        self,
        user_id,
        *,
        smtp_host,
        smtp_port,
        smtp_password=None,
    ):
        with self._write_session() as session:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return None
            user.smtp_host = (smtp_host or "").strip() or None
            user.smtp_port = int(smtp_port) if smtp_port else None
            if smtp_password is not None:
                user.smtp_password = smtp_password.strip() or None
            session.flush()
            return user

    def list_meeting_ids_for_user(self, user_id):
        with self._read_session() as session:
            rows = (
                session.query(Meeting.id)
                .filter(Meeting.user_id == user_id)
                .order_by(Meeting.created_at.desc())
                .all()
            )
            return [row.id for row in rows]

    def create_meeting(
        self,
        title,
        audio_path,
        duration_category,
        environment,
        file_hash="",
        user_id=None,
        created_at=None,
        is_private=False,
    ):
        with self._write_session() as session:
            owner_id = user_id or self._ensure_default_user(session).id
            meeting = Meeting(
                user_id=owner_id,
                title=title,
                audio_path=audio_path,
                duration_category=duration_category,
                environment=environment,
                file_hash=file_hash,
                created_at=created_at or datetime.now(),
                is_private=is_private,
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
        user_id=None,
    ):
        with self._write_session() as session:
            query = session.query(Meeting).filter_by(id=meeting_id)
            meeting = self._apply_user_filter(query, user_id).first()
            if meeting:
                meeting.minutes_text = minutes
                meeting.action_items_text = action_items
                meeting.resolutions_text = resolutions
                if short_summary is not None:
                    meeting.short_summary = short_summary
                if project_name is not None:
                    meeting.project_name = project_name
                meeting.updated_at = datetime.now()

    def update_meeting_project_name(self, meeting_id, project_name, user_id=None):
        with self._write_session() as session:
            query = session.query(Meeting).filter_by(id=meeting_id)
            meeting = self._apply_user_filter(query, user_id).first()
            if meeting:
                meeting.project_name = project_name[:255]
                meeting.updated_at = datetime.now()
                return True
            return False

    def add_transcriptions_bulk(self, meeting_id, segments, user_id=None):
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
                    "speaker": seg.get("speaker") or seg.get("spk") or "",
                }
            )
        with self._write_session() as session:
            if user_id is not None:
                meeting = (
                    session.query(Meeting.id)
                    .filter(Meeting.id == meeting_id, Meeting.user_id == user_id)
                    .first()
                )
                if not meeting:
                    return
            session.bulk_insert_mappings(Transcription, mappings)

    def replace_transcriptions(self, meeting_id, segments, user_id=None):
        with self._write_session() as session:
            query = session.query(Meeting.id).filter(Meeting.id == meeting_id)
            if user_id is not None:
                query = query.filter(Meeting.user_id == user_id)
            if not query.first():
                return

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
                        "speaker": seg.get("speaker") or seg.get("spk") or "",
                    }
                )
            session.bulk_insert_mappings(Transcription, mappings)

    def delete_meeting(self, meeting_id, user_id=None):
        with self._write_session() as session:
            query = session.query(Meeting).filter_by(id=meeting_id)
            meeting = self._apply_user_filter(query, user_id).first()
            if meeting:
                session.delete(meeting)
                return True
            return False

    def get_meeting_by_hash(self, file_hash, user_id=None):
        if not file_hash:
            return None
        with self._read_session() as session:
            query = (
                session.query(Meeting)
                .options(joinedload(Meeting.transcriptions))
                .filter_by(file_hash=file_hash)
            )
            query = self._apply_user_filter(query, user_id)
            return query.first()

    def get_all_meetings(self, user_id=None):
        with self._read_session() as session:
            query = session.query(Meeting).options(joinedload(Meeting.transcriptions))
            query = self._apply_user_filter(query, user_id)
            return query.order_by(Meeting.created_at.desc()).all()

    def _month_bucket_expr(self, session):
        dialect = session.get_bind().dialect.name
        if dialect == "sqlite":
            return func.strftime("%Y-%m", Meeting.created_at)
        return func.to_char(Meeting.created_at, "YYYY-MM")

    def get_stats_overview_data(self, user_id=None):
        with self._read_session() as session:
            summary_query = session.query(
                func.count(Meeting.id).label("total_meetings"),
                func.coalesce(
                    func.sum(case((Meeting.duration_category == "short", 1), else_=0)),
                    0,
                ).label("short_meetings"),
                func.coalesce(
                    func.sum(case((Meeting.duration_category == "medium", 1), else_=0)),
                    0,
                ).label("medium_meetings"),
                func.coalesce(
                    func.sum(case((Meeting.duration_category == "long", 1), else_=0)),
                    0,
                ).label("long_meetings"),
                func.coalesce(
                    func.sum(case((Meeting.environment == "multi_speaker", 1), else_=0)),
                    0,
                ).label("multi_speaker_meetings"),
            )
            summary = self._apply_user_filter(summary_query, user_id).one()

            todo_summary_query = session.query(
                func.count(TodoItem.id).label("total_todos"),
                func.coalesce(
                    func.sum(case((TodoItem.status == "done", 1), else_=0)),
                    0,
                ).label("completed_todos"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (TodoItem.status == "pending")
                                & TodoItem.due_date.isnot(None)
                                & (TodoItem.due_date < datetime.now()),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("overdue_todos"),
            )
            if user_id is not None:
                todo_summary_query = todo_summary_query.filter(TodoItem.user_id == user_id)
            todo_summary = todo_summary_query.one()

            assignee_query = session.query(
                func.coalesce(TodoItem.assignee, "未指定").label("key"),
                func.count(TodoItem.id).label("count"),
            ).filter(TodoItem.status != "cancelled")
            if user_id is not None:
                assignee_query = assignee_query.filter(TodoItem.user_id == user_id)
            assignee_rows = (
                assignee_query.group_by(func.coalesce(TodoItem.assignee, "未指定"))
                .order_by(
                    func.count(TodoItem.id).desc(),
                    func.coalesce(TodoItem.assignee, "未指定").asc(),
                )
                .all()
            )

            duration_query = (
                session.query(
                    Meeting.duration_category.label("key"),
                    func.count(Meeting.id).label("count"),
                )
                .filter(Meeting.duration_category.isnot(None))
            )
            duration_rows = (
                self._apply_user_filter(duration_query, user_id)
                .group_by(Meeting.duration_category)
                .all()
            )

            environment_query = (
                session.query(
                    Meeting.environment.label("key"),
                    func.count(Meeting.id).label("count"),
                )
                .filter(Meeting.environment.isnot(None))
            )
            environment_rows = (
                self._apply_user_filter(environment_query, user_id)
                .group_by(Meeting.environment)
                .all()
            )

            month_bucket = self._month_bucket_expr(session)
            monthly_query = (
                session.query(
                    month_bucket.label("month"),
                    func.count(Meeting.id).label("count"),
                )
                .filter(Meeting.created_at.isnot(None))
            )
            monthly_rows = (
                self._apply_user_filter(monthly_query, user_id)
                .group_by(month_bucket)
                .order_by(month_bucket)
                .all()
            )

            duration_distribution = {key: 0 for key in ("short", "medium", "long")}
            for row in duration_rows:
                if row.key:
                    duration_distribution[row.key] = int(row.count)

            environment_distribution = {
                key: 0 for key in ("quiet", "noisy", "multi_speaker", "unknown")
            }
            for row in environment_rows:
                if row.key:
                    environment_distribution[row.key] = int(row.count)

            monthly_trend = [
                {"month": row.month, "count": int(row.count)}
                for row in monthly_rows
                if row.month
            ]

            return {
                "total_meetings": int(summary.total_meetings or 0),
                "short_meetings": int(summary.short_meetings or 0),
                "medium_meetings": int(summary.medium_meetings or 0),
                "long_meetings": int(summary.long_meetings or 0),
                "multi_speaker_meetings": int(summary.multi_speaker_meetings or 0),
                "total_todos": int(todo_summary.total_todos or 0),
                "completed_todos": int(todo_summary.completed_todos or 0),
                "overdue_todos": int(todo_summary.overdue_todos or 0),
                "todo_assignee_distribution": [
                    {"key": row.key, "count": int(row.count)} for row in assignee_rows
                ],
                "duration_distribution": duration_distribution,
                "environment_distribution": environment_distribution,
                "monthly_trend": monthly_trend,
            }

    def get_all_meetings_safe(self, user_id=None):
        from sqlalchemy import inspect, text

        with self._read_session() as session:
            inspector = inspect(session.get_bind())
            cols = [col["name"] for col in inspector.get_columns("meetings")]
            has_modern_schema = all(
                name in cols for name in ("short_summary", "project_name", "user_id")
            )

            if has_modern_schema:
                query = session.query(Meeting).options(joinedload(Meeting.transcriptions))
                query = self._apply_user_filter(query, user_id)
                return query.order_by(Meeting.created_at.desc()).all()

            select_fields = [
                "id",
                "title",
                "created_at",
                "updated_at",
                "audio_path",
                "duration_category",
                "environment",
                "file_hash",
                "minutes_text",
                "action_items_text",
                "resolutions_text",
            ]
            if "user_id" in cols:
                select_fields.insert(1, "user_id")
            sql = f"SELECT {', '.join(select_fields)} FROM meetings"
            params = {}
            if user_id is not None and "user_id" in cols:
                sql += " WHERE user_id = :user_id"
                params["user_id"] = user_id
            sql += " ORDER BY created_at DESC"
            rows = session.execute(text(sql), params).fetchall()

            meetings = []
            for row in rows:
                meetings.append(
                    Meeting(
                        id=row.id,
                        user_id=getattr(row, "user_id", None),
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
                )
            return meetings

    def get_meetings_paginated(
        self,
        page=0,
        page_size=10,
        search="",
        dur_filter=None,
        env_filter=None,
        user_id=None,
    ):
        with self._read_session() as session:
            query = session.query(Meeting)
            query = self._apply_user_filter(query, user_id)

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
                mapping = {
                    "安静": "quiet",
                    "嘈杂": "noisy",
                    "多人": "multi_speaker",
                    "未知": "unknown",
                }
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

    def get_meeting_by_id(self, meeting_id, user_id=None):
        with self._read_session() as session:
            query = (
                session.query(Meeting)
                .options(joinedload(Meeting.transcriptions))
                .filter_by(id=meeting_id)
            )
            query = self._apply_user_filter(query, user_id)
            return query.first()

    # Contact management

    def list_contacts(self, user_id: int):
        with self._read_session() as session:
            return (
                session.query(Contact)
                .options(joinedload(Contact.groups).joinedload(ContactGroup.contacts))
                .filter(Contact.user_id == user_id)
                .order_by(Contact.name.asc(), Contact.id.asc())
                .all()
            )

    def get_contact(self, contact_id: int, user_id: int):
        with self._read_session() as session:
            return (
                session.query(Contact)
                .options(joinedload(Contact.groups).joinedload(ContactGroup.contacts))
                .filter(Contact.id == contact_id, Contact.user_id == user_id)
                .first()
            )

    def create_contact(
        self,
        user_id: int,
        name: str,
        email: str,
        note: str = "",
        group_ids: list[int] | None = None,
    ):
        with self._write_session() as session:
            contact = Contact(
                user_id=user_id,
                name=name,
                email=email,
                note=note,
                created_at=datetime.now(),
            )
            session.add(contact)
            session.flush()
            if group_ids:
                groups = (
                    session.query(ContactGroup)
                    .filter(
                        ContactGroup.user_id == user_id,
                        ContactGroup.id.in_(group_ids),
                    )
                    .all()
                )
                contact.groups = groups
            session.flush()
            return (
                session.query(Contact)
                .options(joinedload(Contact.groups).joinedload(ContactGroup.contacts))
                .filter(Contact.id == contact.id, Contact.user_id == user_id)
                .first()
            )

    def update_contact(
        self,
        user_id: int,
        contact_id: int,
        *,
        name: str,
        email: str,
        note: str = "",
        group_ids: list[int] | None = None,
    ):
        with self._write_session() as session:
            contact = (
                session.query(Contact)
                .options(joinedload(Contact.groups))
                .filter(Contact.id == contact_id, Contact.user_id == user_id)
                .first()
            )
            if not contact:
                return None

            contact.name = name
            contact.email = email
            contact.note = note
            groups = []
            if group_ids:
                groups = (
                    session.query(ContactGroup)
                    .filter(
                        ContactGroup.user_id == user_id,
                        ContactGroup.id.in_(group_ids),
                    )
                    .all()
                )
            contact.groups = groups
            session.flush()
            return (
                session.query(Contact)
                .options(joinedload(Contact.groups).joinedload(ContactGroup.contacts))
                .filter(Contact.id == contact.id, Contact.user_id == user_id)
                .first()
            )

    def delete_contact(self, user_id: int, contact_id: int) -> bool:
        with self._write_session() as session:
            contact = (
                session.query(Contact)
                .filter(Contact.id == contact_id, Contact.user_id == user_id)
                .first()
            )
            if not contact:
                return False
            session.delete(contact)
            return True

    def list_contact_groups(self, user_id: int):
        with self._read_session() as session:
            return (
                session.query(ContactGroup)
                .options(joinedload(ContactGroup.contacts))
                .filter(ContactGroup.user_id == user_id)
                .order_by(ContactGroup.group_name.asc(), ContactGroup.id.asc())
                .all()
            )

    def get_contact_group(self, group_id: int, user_id: int):
        with self._read_session() as session:
            return (
                session.query(ContactGroup)
                .options(joinedload(ContactGroup.contacts))
                .filter(ContactGroup.id == group_id, ContactGroup.user_id == user_id)
                .first()
            )

    def create_contact_group(
        self,
        user_id: int,
        group_name: str,
        member_ids: list[int] | None = None,
    ):
        with self._write_session() as session:
            group = ContactGroup(
                user_id=user_id,
                group_name=group_name,
                created_at=datetime.now(),
            )
            session.add(group)
            session.flush()
            if member_ids:
                members = (
                    session.query(Contact)
                    .filter(Contact.user_id == user_id, Contact.id.in_(member_ids))
                    .all()
                )
                group.contacts = members
            session.refresh(group)
            return group

    def update_contact_group(
        self,
        user_id: int,
        group_id: int,
        *,
        group_name: str,
        member_ids: list[int] | None = None,
    ):
        with self._write_session() as session:
            group = (
                session.query(ContactGroup)
                .options(joinedload(ContactGroup.contacts))
                .filter(ContactGroup.id == group_id, ContactGroup.user_id == user_id)
                .first()
            )
            if not group:
                return None

            group.group_name = group_name
            members = []
            if member_ids:
                members = (
                    session.query(Contact)
                    .filter(Contact.user_id == user_id, Contact.id.in_(member_ids))
                    .all()
                )
            group.contacts = members
            session.flush()
            session.refresh(group)
            return group

    def delete_contact_group(self, user_id: int, group_id: int) -> bool:
        with self._write_session() as session:
            group = (
                session.query(ContactGroup)
                .filter(ContactGroup.id == group_id, ContactGroup.user_id == user_id)
                .first()
            )
            if not group:
                return False
            session.delete(group)
            return True

    # Email logs

    def add_email_log(
        self,
        meeting_id: int,
        recipient_email: str,
        status: str,
        error_msg: str | None = None,
        *,
        user_id: int | None = None,
    ):
        with self._write_session() as session:
            meeting_query = session.query(Meeting.id).filter(Meeting.id == meeting_id)
            if user_id is not None:
                meeting_query = meeting_query.filter(Meeting.user_id == user_id)
            if not meeting_query.first():
                return None

            log = EmailLog(
                meeting_id=meeting_id,
                recipient_email=recipient_email,
                status=status,
                error_msg=error_msg,
                sent_at=datetime.now(),
            )
            session.add(log)
            session.flush()
            return log

    def get_email_logs(self, meeting_id: int, *, user_id: int | None = None):
        with self._read_session() as session:
            query = (
                session.query(EmailLog)
                .join(Meeting, Meeting.id == EmailLog.meeting_id)
                .filter(EmailLog.meeting_id == meeting_id)
            )
            if user_id is not None:
                query = query.filter(Meeting.user_id == user_id)
            return query.order_by(EmailLog.sent_at.desc(), EmailLog.id.desc()).all()
