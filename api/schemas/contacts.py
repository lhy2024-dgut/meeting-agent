from datetime import datetime

from pydantic import BaseModel, Field


class ContactCreateRequest(BaseModel):
    name: str
    email: str
    note: str = ""
    group_ids: list[int] = Field(default_factory=list)


class ContactUpdateRequest(BaseModel):
    name: str
    email: str
    note: str = ""
    group_ids: list[int] = Field(default_factory=list)


class ContactGroupCreateRequest(BaseModel):
    group_name: str
    member_ids: list[int] = Field(default_factory=list)


class ContactGroupUpdateRequest(BaseModel):
    group_name: str
    member_ids: list[int] = Field(default_factory=list)


class ContactGroupSummary(BaseModel):
    id: int
    group_name: str
    member_count: int


class ContactResponse(BaseModel):
    id: int
    name: str
    email: str
    note: str
    created_at: datetime | None = None
    groups: list[ContactGroupSummary]


class ContactListResponse(BaseModel):
    items: list[ContactResponse]


class ContactMemberSummary(BaseModel):
    id: int
    name: str
    email: str


class ContactGroupResponse(BaseModel):
    id: int
    group_name: str
    created_at: datetime | None = None
    members: list[ContactMemberSummary]


class ContactGroupListResponse(BaseModel):
    items: list[ContactGroupResponse]


class EmailLogResponse(BaseModel):
    id: int
    recipient_email: str
    status: str
    error_msg: str | None = None
    sent_at: datetime | None = None


class EmailLogListResponse(BaseModel):
    items: list[EmailLogResponse]


class MeetingEmailSendRequest(BaseModel):
    recipient_emails: list[str]
    subject: str
    attach_minutes_document: bool = True
    document_format: str = "docx"
    attach_html_summary: bool = False


class EmailSendItemResponse(BaseModel):
    email: str
    success: bool
    error: str | None = None


class MeetingEmailSendResponse(BaseModel):
    success_count: int
    failure_count: int
    items: list[EmailSendItemResponse]
    warnings: list[str] = Field(default_factory=list)
