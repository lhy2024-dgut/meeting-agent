from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

import config
from services.auth_service import verify_password

MEETING_UNLOCK_TOKEN_TYPE = "meeting_unlock"
CROSS_PRIVATE_CHAT_TOKEN_TYPE = "cross_private_chat"
DEFAULT_UNLOCK_TTL_MINUTES = 60


class PrivacyError(ValueError):
    pass


def verify_unlock_password(user, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise PrivacyError("Invalid password")


def _build_unlock_token(
    *,
    user_id: int,
    token_version: int,
    token_type: str,
    scope: str,
    expires_in_minutes: int,
    meeting_id: int | None = None,
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expires_in_minutes)
    payload: dict[str, object] = {
        "sub": str(user_id),
        "ver": token_version,
        "type": token_type,
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if meeting_id is not None:
        payload["meeting_id"] = meeting_id
    token = jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)
    return token, expires_at


def create_meeting_unlock_token(
    *,
    user_id: int,
    token_version: int,
    meeting_id: int,
    expires_in_minutes: int = DEFAULT_UNLOCK_TTL_MINUTES,
) -> tuple[str, datetime]:
    return _build_unlock_token(
        user_id=user_id,
        token_version=token_version,
        token_type=MEETING_UNLOCK_TOKEN_TYPE,
        scope="meeting",
        expires_in_minutes=expires_in_minutes,
        meeting_id=meeting_id,
    )


def create_cross_private_chat_token(
    *,
    user_id: int,
    token_version: int,
    expires_in_minutes: int = DEFAULT_UNLOCK_TTL_MINUTES,
) -> tuple[str, datetime]:
    return _build_unlock_token(
        user_id=user_id,
        token_version=token_version,
        token_type=CROSS_PRIVATE_CHAT_TOKEN_TYPE,
        scope="cross_private_chat",
        expires_in_minutes=expires_in_minutes,
    )


def decode_unlock_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise PrivacyError("Invalid unlock token") from exc
    return payload


def validate_unlock_token(
    token: str,
    *,
    expected_type: str,
    user_id: int,
    token_version: int,
    meeting_id: int | None = None,
) -> dict:
    payload = decode_unlock_token(token)

    if payload.get("type") != expected_type:
        raise PrivacyError("Unexpected unlock token type")
    if str(payload.get("sub")) != str(user_id):
        raise PrivacyError("Unlock token does not belong to the current user")
    if int(payload.get("ver", -1)) != int(token_version or 0):
        raise PrivacyError("Unlock token has been revoked")
    if meeting_id is not None and int(payload.get("meeting_id", -1)) != int(meeting_id):
        raise PrivacyError("Unlock token does not match this meeting")
    return payload
