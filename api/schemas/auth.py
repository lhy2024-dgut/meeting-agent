from datetime import datetime

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    login: str
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthMutationResponse(BaseModel):
    success: bool


class CurrentUserResponse(BaseModel):
    id: int
    username: str
    email: str
    display_name: str
    created_at: datetime | None = None
    last_login_at: datetime | None = None
