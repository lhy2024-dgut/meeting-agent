# models.py — pgvector 降级版
# embedding 字段改用 Text 存储 JSON 字符串，待 pgvector 安装成功后恢复
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
    chunk_text = Column(Text, nullable=False)
    # 原来是 Vector 类型，临时改为 Text 存 JSON 字符串
    # 待 pgvector 安装成功后改回：from pgvector.sqlalchemy import Vector; embedding = Column(Vector(1024))
    embedding = Column(Text)
