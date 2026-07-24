from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user, get_meeting_repository
from api.schemas.privacy import PrivacyUnlockRequest, PrivacyUnlockResponse
from db.repository import MeetingRepository
from services.auth_service import verify_password
from services.privacy_service import (
    create_cross_private_chat_token,
    create_meeting_unlock_token,
)

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


@router.post("/unlock", response_model=PrivacyUnlockResponse)
def unlock_privacy_scope(
    payload: PrivacyUnlockRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> PrivacyUnlockResponse:
    if payload.scope == "meeting":
        if payload.meeting_id is None:
            raise HTTPException(status_code=400, detail="meeting_id is required")
        meeting = repo.get_meeting_by_id(payload.meeting_id, user_id=current_user.id)
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        if not getattr(meeting, "is_private", False):
            raise HTTPException(status_code=400, detail="Meeting is not private")
        if not verify_password(payload.password, current_user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid password")
        token, expires_at = create_meeting_unlock_token(
            user_id=current_user.id,
            token_version=current_user.token_version or 0,
            meeting_id=payload.meeting_id,
        )
        return PrivacyUnlockResponse(
            unlock_token=token,
            expires_at=expires_at,
            scope=payload.scope,
        )

    if payload.scope == "cross_chat_all":
        if not verify_password(payload.password, current_user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid password")
        token, expires_at = create_cross_private_chat_token(
            user_id=current_user.id,
            token_version=current_user.token_version or 0,
        )
        return PrivacyUnlockResponse(
            unlock_token=token,
            expires_at=expires_at,
            scope=payload.scope,
        )

    raise HTTPException(status_code=400, detail="Unsupported privacy scope")
