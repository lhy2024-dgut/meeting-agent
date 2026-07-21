from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    display_name = Column(String(255))
    created_at = Column(DateTime)
    last_login_at = Column(DateTime)
    smtp_host = Column(String(255))
    smtp_port = Column(Integer)
    smtp_password = Column(String(255))

    meetings = relationship("Meeting", back_populates="user", lazy="selectin")
    todos = relationship("TodoItem", back_populates="user", lazy="selectin")
    contacts = relationship("Contact", back_populates="user", lazy="selectin")
    contact_groups = relationship("ContactGroup", back_populates="user", lazy="selectin")


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    audio_path = Column(String(500))
    duration_category = Column(String(50))
    environment = Column(String(100))
    file_hash = Column(String(64), index=True)
    is_private = Column(Boolean, nullable=False, default=False, server_default="false")

    minutes_text = Column(Text)
    action_items_text = Column(Text)
    resolutions_text = Column(Text)
    short_summary = Column(String(500))
    project_name = Column(String(255))

    user = relationship("User", back_populates="meetings", lazy="joined")
    transcriptions = relationship(
        "Transcription",
        back_populates="meeting",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    todos = relationship(
        "TodoItem",
        back_populates="meeting",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    email_logs = relationship(
        "EmailLog",
        back_populates="meeting",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class Transcription(Base):
    __tablename__ = "transcriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(
        Integer, ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    text = Column(Text)
    timestamp = Column(Float)
    start_time = Column(Float)
    end_time = Column(Float)
    audio_segment = Column(String(500))
    summary = Column(Text)
    speaker = Column(String(64))

    meeting = relationship("Meeting", back_populates="transcriptions")


class MeetingChunk(Base):
    __tablename__ = "meeting_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(
        Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_type = Column(String(32), nullable=False, default="unknown")
    chunk_index = Column(Integer, nullable=False, default=0)
    chunk_text = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, default="")
    embedding = Column(Vector(1024))
    created_at = Column(DateTime)


contact_group_members = Table(
    "contact_group_members",
    Base.metadata,
    Column("contact_id", Integer, ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "group_id",
        Integer,
        ForeignKey("contact_groups.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("user_id", "email", name="uq_contacts_user_email"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    note = Column(Text)
    created_at = Column(DateTime)

    user = relationship("User", back_populates="contacts", lazy="joined")
    groups = relationship(
        "ContactGroup",
        secondary=contact_group_members,
        back_populates="contacts",
        lazy="selectin",
    )


class ContactGroup(Base):
    __tablename__ = "contact_groups"
    __table_args__ = (
        UniqueConstraint("user_id", "group_name", name="uq_contact_groups_user_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    group_name = Column(String(100), nullable=False)
    created_at = Column(DateTime)

    user = relationship("User", back_populates="contact_groups", lazy="joined")
    contacts = relationship(
        "Contact",
        secondary=contact_group_members,
        back_populates="groups",
        lazy="selectin",
    )


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(
        Integer,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    recipient_email = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    error_msg = Column(Text)
    sent_at = Column(DateTime)

    meeting = relationship("Meeting", back_populates="email_logs", lazy="joined")


class TodoItem(Base):
    __tablename__ = "todo_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'done', 'cancelled')",
            name="ck_todo_items_status_valid",
        ),
        CheckConstraint(
            "priority IN ('high', 'medium', 'low')",
            name="ck_todo_items_priority_valid",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    meeting_id = Column(
        Integer,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    content = Column(Text, nullable=False)
    assignee = Column(String(255))
    due_date = Column(DateTime)
    status = Column(String(32), nullable=False, default="pending")
    priority = Column(String(32), nullable=False, default="medium")
    source = Column(String(32), nullable=False, default="meeting_pipeline")
    is_user_modified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    user = relationship("User", back_populates="todos", lazy="joined")
    meeting = relationship("Meeting", back_populates="todos", lazy="joined")
    status_logs = relationship(
        "TodoStatusLog",
        back_populates="todo",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class TodoStatusLog(Base):
    __tablename__ = "todo_status_logs"
    __table_args__ = (
        CheckConstraint(
            "to_status IN ('pending', 'done', 'cancelled')",
            name="ck_todo_status_logs_to_status_valid",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    todo_id = Column(
        Integer,
        ForeignKey("todo_items.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    from_status = Column(String(32))
    to_status = Column(String(32), nullable=False)
    changed_by = Column(String(32), nullable=False, default="manual")
    changed_at = Column(DateTime)
    reason = Column(Text)

    todo = relationship("TodoItem", back_populates="status_logs", lazy="joined")
