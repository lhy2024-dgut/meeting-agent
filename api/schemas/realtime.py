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


class RealtimeGenerateRequest(BaseModel):
    is_private: bool = False


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
    dropped_chunk_count: int = 0            # 解码连续失败被跳过的分片数（录音缺该段）
    transcription_failed_count: int = 0     # 转写失败但录音保留的分片数（文字缺该段）
    segments: list[RealtimeSegment]
    speaker_segments: list[RealtimeSegment]
    created_at: datetime
    updated_at: datetime


class RealtimeSessionMutationResponse(BaseModel):
    success: bool
