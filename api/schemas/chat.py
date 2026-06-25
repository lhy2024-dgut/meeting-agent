from pydantic import BaseModel


class ChatSessionCreateRequest(BaseModel):
    mode: str = "single"
    meeting_id: int | None = None


class ChatSessionCreateResponse(BaseModel):
    session_id: str
    mode: str
    meeting_id: int | None = None


class ChatMessageRequest(BaseModel):
    message: str


class ChatMemoryStats(BaseModel):
    round_count: int
    max_rounds: int
    is_full: bool
    trimmed: bool


class RagResultItem(BaseModel):
    meeting_id: int | None = None
    chunk_type: str | None = None
    meeting_title: str | None = None
    meeting_summary: str | None = None
    chunk_type_label: str | None = None
    text: str = ""
    score: float = 0.0


class ChatMessageResponse(BaseModel):
    assistant_message: str
    rag_results: list[RagResultItem]
    memory: ChatMemoryStats
