from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(255))
    created_at = Column(DateTime)
    last_login_at = Column(DateTime)

    meetings = relationship("Meeting", back_populates="user", lazy="selectin")
    todos = relationship("TodoItem", back_populates="user", lazy="selectin")


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


class TodoItem(Base):
    __tablename__ = "todo_items"

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
