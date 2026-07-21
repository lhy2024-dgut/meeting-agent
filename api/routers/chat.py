from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user, get_meeting_repository
from api.schemas.chat import (
    ChatMemoryStats,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionCreateRequest,
    ChatSessionCreateResponse,
    RagResultItem,
)
from api.services.chat_session_manager import chat_session_manager
from db.repository import MeetingRepository
from services.auth_service import decode_token

router = APIRouter(prefix="/api/chat", tags=["chat"])


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


@router.post("/sessions", response_model=ChatSessionCreateResponse)
def create_chat_session(
    payload: ChatSessionCreateRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> ChatSessionCreateResponse:
    mode = payload.mode or "single"
    if mode not in {"single", "cross"}:
        raise HTTPException(status_code=400, detail="Unsupported chat mode")

    transcript = ""
    minutes = ""
    action_items = ""
    resolutions = ""
    meeting_id = payload.meeting_id
    meeting_ids = None

    if mode == "single":
        if not meeting_id:
            raise HTTPException(status_code=400, detail="meeting_id is required for single mode")
        meeting = repo.get_meeting_by_id(meeting_id, user_id=current_user.id)
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        _require_private_unlock(meeting, current_user, payload.unlock_token)
        transcript = " ".join(item.text or "" for item in meeting.transcriptions)
        minutes = meeting.minutes_text or ""
        action_items = meeting.action_items_text or ""
        resolutions = meeting.resolutions_text or ""
    else:
        meeting_ids = [
            item.id
            for item in repo.get_all_meetings(user_id=current_user.id)
            if not bool(getattr(item, "is_private", False))
        ]

    session = chat_session_manager.create_session(
        user_id=current_user.id,
        mode=mode,
        meeting_id=meeting_id,
        meeting_ids=meeting_ids,
        transcript=transcript,
        minutes=minutes,
        action_items=action_items,
        resolutions=resolutions,
    )
    return ChatSessionCreateResponse(
        session_id=session.session_id,
        mode=session.mode,
        meeting_id=session.meeting_id,
    )


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
def send_chat_message(
    session_id: str,
    payload: ChatMessageRequest,
    current_user=Depends(get_current_user),
) -> ChatMessageResponse:
    session = chat_session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Chat session does not belong to the current user")

    validation_error = session.agent.validate_input(payload.message)
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)

    try:
        assistant_message = session.agent.chat(payload.message)
        rag_results = [
            RagResultItem(
                meeting_id=item.get("meeting_id"),
                chunk_type=item.get("chunk_type"),
                meeting_title=item.get("meeting_title"),
                meeting_summary=item.get("meeting_summary"),
                chunk_type_label=item.get("chunk_type_label"),
                text=item.get("text", ""),
                score=float(item.get("score", 0)),
            )
            for item in session.agent.get_latest_rag_results()
        ]
        memory = ChatMemoryStats(**session.agent.get_memory_stats())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatMessageResponse(
        assistant_message=assistant_message,
        rag_results=rag_results,
        memory=memory,
    )
