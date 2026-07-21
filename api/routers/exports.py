from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from api.deps import get_current_user, get_meeting_repository
from chains.export_chain import ExportChain
from db.repository import MeetingRepository
from services.auth_service import decode_token

router = APIRouter(prefix="/api/meetings", tags=["exports"])


def _get_owned_meeting(repo: MeetingRepository, meeting_id: int, user_id: int):
    meeting = repo.get_meeting_by_id(meeting_id, user_id=user_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


def _require_private_unlock(meeting, current_user, unlock_token: str | None) -> None:
    if not bool(getattr(meeting, "is_private", False)):
        return
    if not unlock_token:
        raise HTTPException(status_code=403, detail="Meeting unlock required")
    try:
        payload = decode_token(unlock_token, expected_type="meeting_unlock")
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Invalid meeting unlock token") from exc
    if int(payload.get("sub", 0)) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Invalid meeting unlock token")
    if int(payload.get("meeting_id", 0)) != int(meeting.id):
        raise HTTPException(status_code=403, detail="Invalid meeting unlock token")
    if payload.get("ver") != (current_user.token_version or 0):
        raise HTTPException(status_code=403, detail="Invalid meeting unlock token")


@router.post("/{meeting_id}/exports")
def create_export(
    meeting_id: int,
    format: str = Query("docx"),
    unlock_token: str | None = Query(default=None),
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> dict[str, str]:
    meeting = _get_owned_meeting(repo, meeting_id, current_user.id)
    _require_private_unlock(meeting, current_user, unlock_token)
    exporter = ExportChain()
    data = {
        "meeting_id": meeting.id,
        "title": meeting.title,
        "date": meeting.created_at.strftime("%Y-%m-%d %H:%M") if meeting.created_at else "",
        "minutes": meeting.minutes_text or "",
        "action_items": meeting.action_items_text or "",
        "resolutions": meeting.resolutions_text or "",
    }
    output_path = exporter.run(data, output_format=format)
    return {"output_path": output_path}


@router.get("/{meeting_id}/exports/download")
def download_export(
    meeting_id: int,
    format: str = Query("docx"),
    unlock_token: str | None = Query(default=None),
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> FileResponse:
    meeting = _get_owned_meeting(repo, meeting_id, current_user.id)
    _require_private_unlock(meeting, current_user, unlock_token)
    exporter = ExportChain()
    data = {
        "meeting_id": meeting.id,
        "title": meeting.title,
        "date": meeting.created_at.strftime("%Y-%m-%d %H:%M") if meeting.created_at else "",
        "minutes": meeting.minutes_text or "",
        "action_items": meeting.action_items_text or "",
        "resolutions": meeting.resolutions_text or "",
    }
    output_path = exporter.run(data, output_format=format)
    path = Path(output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export file not found")

    media_type = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "md": "text/markdown; charset=utf-8",
        "pdf": "application/pdf",
    }.get(format, "application/octet-stream")

    return FileResponse(
        path,
        media_type=media_type,
        filename=f"meeting_{meeting_id}.{format}",
    )
