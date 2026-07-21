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
    smtp_configured: bool = False


class UpdateProfileRequest(BaseModel):
    display_name: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class VerifyPasswordRequest(BaseModel):
    password: str


class VerifyPasswordResponse(BaseModel):
    valid: bool


class UserSmtpSettingsResponse(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_from: str
    smtp_password_configured: bool
    using_global_fallback: bool = False


class UpdateUserSmtpSettingsRequest(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_password: str = ""


class TestSmtpSettingsRequest(BaseModel):
    recipient_email: str = ""


class SmtpTestResponse(BaseModel):
    success: bool
    recipient_email: str
    error: str | None = None
