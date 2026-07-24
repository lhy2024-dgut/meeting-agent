from datetime import datetime

from pydantic import BaseModel

from api.schemas.todos import TodoItemResponse


class MeetingSummary(BaseModel):
    id: int
    title: str
    is_private: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    duration_category: str
    duration_label: str
    environment: str
    environment_label: str
    short_summary: str
    project_name: str
    action_item_count: int
    resolution_count: int


class MeetingListResponse(BaseModel):
    items: list[MeetingSummary]
    page: int
    page_size: int
    total: int
    total_pages: int


class MeetingProjectUpdateRequest(BaseModel):
    project_name: str


class MeetingMutationResponse(BaseModel):
    success: bool


class MeetingTermsResponse(BaseModel):
    meeting_id: int
    terms: list[str]


class MeetingDetail(BaseModel):
    id: int
    title: str
    is_private: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    date_text: str
    duration_category: str
    duration_label: str
    environment: str
    environment_label: str
    duration_seconds: float
    duration_display: str
    minutes_text: str
    action_items_text: str
    resolutions_text: str
    short_summary: str
    project_name: str
    action_item_count: int
    resolution_count: int
    transcript_count: int
    todos: list[TodoItemResponse]


class TranscriptSegment(BaseModel):
    id: int
    text: str
    timestamp: float
    start_time: float
    end_time: float


class TranscriptResponse(BaseModel):
    meeting_id: int
    updated_at: datetime
    full_text: str
    segments: list[TranscriptSegment]


class HtmlSummaryGenerateRequest(BaseModel):
    show_code: bool = False
    show_flowchart: bool = True


class HtmlSummaryResponse(BaseModel):
    meeting_id: int
    html: str
    file_name: str
    updated_at: datetime
