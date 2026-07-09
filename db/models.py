from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, autoincrement=True)
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

    transcriptions = relationship(
        "Transcription",
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


contact_group_members = Table(
    "contact_group_members",
    Base.metadata,
    Column("contact_id", Integer, ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("contact_groups.id", ondelete="CASCADE"), primary_key=True),
)


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    note = Column(Text)
    created_at = Column(DateTime)

    groups = relationship("ContactGroup", secondary=contact_group_members, back_populates="contacts")


class ContactGroup(Base):
    __tablename__ = "contact_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_name = Column(String(100), nullable=False)
    created_at = Column(DateTime)

    contacts = relationship("Contact", secondary=contact_group_members, back_populates="groups")


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_email = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    error_msg = Column(Text)
    sent_at = Column(DateTime)
