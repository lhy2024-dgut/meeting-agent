from datetime import datetime

from pydantic import BaseModel


class RealtimeSegment(BaseModel):
    start: float
    end: float
    timestamp: float
    text: str
    speaker: str | None = None


class RealtimeSessionCreateRequest(BaseModel):
    title: str = ""
    meeting_date: str
    meeting_time: str
    output_format: str = "docx"
    scene: str = "通用会议"
    asr_model: str = "faster-whisper"
    terms: list[str] = []


class RealtimeSessionResponse(BaseModel):
    session_id: str
    title: str
    meeting_date: str
    meeting_time: str
    output_format: str
    scene: str
    asr_model: str
    terms: list[str]
    status: str
    message: str
    transcript: str
    duration_seconds: float
    chunk_count: int
    segments: list[RealtimeSegment]
    speaker_segments: list[RealtimeSegment]
    created_at: datetime
    updated_at: datetime


class RealtimeSessionMutationResponse(BaseModel):
    success: bool
