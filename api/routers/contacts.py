from __future__ import annotations

from datetime import datetime
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError

from api.deps import get_current_user, get_meeting_repository
from api.schemas.contacts import (
    ContactCreateRequest,
    ContactGroupCreateRequest,
    ContactGroupListResponse,
    ContactGroupResponse,
    ContactGroupSummary,
    ContactGroupUpdateRequest,
    ContactListResponse,
    ContactMemberSummary,
    ContactResponse,
    ContactUpdateRequest,
    EmailLogListResponse,
    EmailLogResponse,
    EmailSendItemResponse,
    MeetingEmailSendRequest,
    MeetingEmailSendResponse,
)
from chains.export_chain import ExportChain
from chains.html_summary_chain import get_html_summary_path
from db.repository import MeetingRepository
from services.email_service import EmailService, build_email_html, check_smtp_config
from services.email_service import SmtpSettings, get_global_smtp_settings
from services.privacy_service import MEETING_UNLOCK_TOKEN_TYPE, PrivacyError, validate_unlock_token

router = APIRouter(prefix="/api", tags=["contacts"])

_ALLOWED_DOCUMENT_FORMATS = {"docx", "md", "pdf"}
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _validate_email(value: str) -> str:
    normalized = _normalize_email(value)
    if not _EMAIL_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail=f"Invalid email address: {value}")
    return normalized


def _serialize_group_summary(group) -> ContactGroupSummary:
    return ContactGroupSummary(
        id=group.id,
        group_name=group.group_name,
        member_count=len(group.contacts or []),
    )


def _serialize_contact(contact) -> ContactResponse:
    groups = sorted(contact.groups or [], key=lambda item: (item.group_name or "", item.id))
    return ContactResponse(
        id=contact.id,
        name=contact.name,
        email=contact.email,
        note=contact.note or "",
        created_at=contact.created_at,
        groups=[_serialize_group_summary(group) for group in groups],
    )


def _serialize_group(group) -> ContactGroupResponse:
    members = sorted(group.contacts or [], key=lambda item: (item.name or "", item.id))
    return ContactGroupResponse(
        id=group.id,
        group_name=group.group_name,
        created_at=group.created_at,
        members=[
            ContactMemberSummary(id=member.id, name=member.name, email=member.email)
            for member in members
        ],
    )


def _serialize_email_log(item) -> EmailLogResponse:
    return EmailLogResponse(
        id=item.id,
        recipient_email=item.recipient_email,
        status=item.status,
        error_msg=item.error_msg,
        sent_at=item.sent_at,
    )


def _resolve_email_service_settings(current_user) -> tuple[SmtpSettings | None, str | None]:
    user_host = (current_user.smtp_host or "").strip()
    user_password = (current_user.smtp_password or "").strip()
    user_port = int(current_user.smtp_port or 0)

    if user_host or user_password or current_user.smtp_port:
        if not user_host or not user_password or user_port <= 0:
            return None, "Your SMTP settings are incomplete"
        return (
            SmtpSettings(
                host=user_host,
                port=user_port,
                user=current_user.email,
                password=user_password,
                from_addr=current_user.email,
            ),
            None,
        )

    global_settings = get_global_smtp_settings()
    smtp_ok, smtp_error = check_smtp_config(global_settings)
    if not smtp_ok:
        return None, smtp_error
    return global_settings, None


def _require_private_meeting_access(meeting, current_user, unlock_token: str | None) -> None:
    if not getattr(meeting, "is_private", False):
        return
    if not unlock_token:
        raise HTTPException(status_code=403, detail="Meeting is private and requires unlock")
    try:
        validate_unlock_token(
            unlock_token,
            expected_type=MEETING_UNLOCK_TOKEN_TYPE,
            user_id=current_user.id,
            token_version=current_user.token_version or 0,
            meeting_id=meeting.id,
        )
    except PrivacyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/contacts", response_model=ContactListResponse)
def list_contacts(
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> ContactListResponse:
    items = repo.list_contacts(current_user.id)
    return ContactListResponse(items=[_serialize_contact(item) for item in items])


@router.post("/contacts", response_model=ContactResponse)
def create_contact(
    payload: ContactCreateRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> ContactResponse:
    try:
        contact = repo.create_contact(
            current_user.id,
            payload.name.strip(),
            _validate_email(payload.email),
            payload.note.strip(),
            payload.group_ids,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Contact email already exists") from exc
    return _serialize_contact(contact)


@router.patch("/contacts/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: int,
    payload: ContactUpdateRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> ContactResponse:
    try:
        contact = repo.update_contact(
            current_user.id,
            contact_id,
            name=payload.name.strip(),
            email=_validate_email(payload.email),
            note=payload.note.strip(),
            group_ids=payload.group_ids,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Contact email already exists") from exc
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _serialize_contact(contact)


@router.delete("/contacts/{contact_id}")
def delete_contact(
    contact_id: int,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> dict[str, bool]:
    success = repo.delete_contact(current_user.id, contact_id)
    if not success:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"success": True}


@router.get("/contact-groups", response_model=ContactGroupListResponse)
def list_contact_groups(
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> ContactGroupListResponse:
    items = repo.list_contact_groups(current_user.id)
    return ContactGroupListResponse(items=[_serialize_group(item) for item in items])


@router.post("/contact-groups", response_model=ContactGroupResponse)
def create_contact_group(
    payload: ContactGroupCreateRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> ContactGroupResponse:
    try:
        group = repo.create_contact_group(
            current_user.id,
            payload.group_name.strip(),
            payload.member_ids,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Group name already exists") from exc
    return _serialize_group(group)


@router.patch("/contact-groups/{group_id}", response_model=ContactGroupResponse)
def update_contact_group(
    group_id: int,
    payload: ContactGroupUpdateRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> ContactGroupResponse:
    try:
        group = repo.update_contact_group(
            current_user.id,
            group_id,
            group_name=payload.group_name.strip(),
            member_ids=payload.member_ids,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Group name already exists") from exc
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return _serialize_group(group)


@router.delete("/contact-groups/{group_id}")
def delete_contact_group(
    group_id: int,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> dict[str, bool]:
    success = repo.delete_contact_group(current_user.id, group_id)
    if not success:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"success": True}


@router.get("/meetings/{meeting_id}/email-logs", response_model=EmailLogListResponse)
def list_meeting_email_logs(
    meeting_id: int,
    unlock_token: str | None = Header(default=None, alias="X-Meeting-Unlock-Token"),
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> EmailLogListResponse:
    meeting = repo.get_meeting_by_id(meeting_id, user_id=current_user.id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _require_private_meeting_access(meeting, current_user, unlock_token)
    logs = repo.get_email_logs(meeting_id, user_id=current_user.id)
    return EmailLogListResponse(items=[_serialize_email_log(item) for item in logs])


@router.post("/meetings/{meeting_id}/emails/send", response_model=MeetingEmailSendResponse)
def send_meeting_email(
    meeting_id: int,
    payload: MeetingEmailSendRequest,
    unlock_token: str | None = Header(default=None, alias="X-Meeting-Unlock-Token"),
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> MeetingEmailSendResponse:
    meeting = repo.get_meeting_by_id(meeting_id, user_id=current_user.id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _require_private_meeting_access(meeting, current_user, unlock_token)

    smtp_settings, smtp_error = _resolve_email_service_settings(current_user)
    if not smtp_settings:
        raise HTTPException(status_code=400, detail=smtp_error or "SMTP is not configured")

    document_format = (payload.document_format or "docx").lower()
    if document_format not in _ALLOWED_DOCUMENT_FORMATS:
        raise HTTPException(status_code=400, detail="Unsupported document format")

    recipients = sorted({_validate_email(email) for email in payload.recipient_emails if email.strip()})
    if not recipients:
        raise HTTPException(status_code=400, detail="At least one recipient is required")

    date_text = (
        meeting.created_at.strftime("%Y-%m-%d %H:%M")
        if isinstance(meeting.created_at, datetime)
        else ""
    )
    minutes = meeting.minutes_text or ""
    action_items = meeting.action_items_text or ""
    resolutions = meeting.resolutions_text or ""
    title = meeting.title or "Meeting Summary"

    body_text = (
        f"会议纪要：{title}\n"
        f"日期：{date_text}\n\n"
        f"=== 会议纪要 ===\n{minutes}\n\n"
        f"=== 待办事项 ===\n{action_items}\n\n"
        f"=== 会议决议 ===\n{resolutions}"
    )
    body_html = build_email_html(title, date_text, minutes, action_items, resolutions)

    attachments: list[str] = []
    warnings: list[str] = []

    if payload.attach_minutes_document:
        exporter = ExportChain()
        export_payload = {
            "meeting_id": meeting.id,
            "title": title,
            "date": date_text,
            "minutes": minutes,
            "action_items": action_items,
            "resolutions": resolutions,
        }
        try:
            attachments.append(exporter.run(export_payload, output_format=document_format))
        except Exception as exc:
            warnings.append(f"Document export failed and was skipped: {exc}")

    if payload.attach_html_summary:
        html_path = get_html_summary_path(meeting_id)
        if html_path.exists():
            attachments.append(str(html_path))
        else:
            warnings.append("HTML summary does not exist yet, so it was skipped")

    service = EmailService(smtp_settings)
    items: list[EmailSendItemResponse] = []
    for recipient in recipients:
        success, error = service.send(
            recipient,
            payload.subject.strip(),
            body_text,
            body_html=body_html,
            attachments=attachments,
        )
        repo.add_email_log(
            meeting_id,
            recipient,
            "success" if success else "failed",
            error,
            user_id=current_user.id,
        )
        items.append(EmailSendItemResponse(email=recipient, success=success, error=error))

    return MeetingEmailSendResponse(
        success_count=sum(1 for item in items if item.success),
        failure_count=sum(1 for item in items if not item.success),
        items=items,
        warnings=warnings,
    )
