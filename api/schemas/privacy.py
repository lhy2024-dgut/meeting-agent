from datetime import datetime

from pydantic import BaseModel


class PrivacyUnlockRequest(BaseModel):
    scope: str
    meeting_id: int | None = None
    password: str


class PrivacyUnlockResponse(BaseModel):
    unlock_token: str
    expires_at: datetime
    scope: str
