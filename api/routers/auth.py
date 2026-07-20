import re

import config
from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_current_user, get_meeting_repository
from api.schemas.auth import (
    AuthMutationResponse,
    ChangePasswordRequest,
    CurrentUserResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    SmtpTestResponse,
    TestSmtpSettingsRequest,
    TokenResponse,
    UpdateProfileRequest,
    UpdateUserSmtpSettingsRequest,
    UserSmtpSettingsResponse,
)
from db.repository import MeetingRepository
from services.auth_service import (
    AuthError,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from services.email_service import (
    EmailService,
    SmtpSettings,
    check_smtp_config,
    get_global_smtp_settings,
    suggest_smtp_settings,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _get_single_account_user(repo: MeetingRepository):
    return repo.get_or_create_default_user()


def _serialize_user(user) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name or user.username,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        smtp_configured=bool((user.smtp_host or "").strip() and (user.smtp_password or "").strip()),
    )


def _serialize_smtp_settings(user) -> UserSmtpSettingsResponse:
    suggested_host, suggested_port = suggest_smtp_settings(user.email)
    host = (user.smtp_host or "").strip() or suggested_host
    port = int(user.smtp_port or suggested_port or 465)
    global_ok, _ = check_smtp_config(get_global_smtp_settings())
    return UserSmtpSettingsResponse(
        smtp_host=host,
        smtp_port=port,
        smtp_user=user.email,
        smtp_from=user.email,
        smtp_password_configured=bool((user.smtp_password or "").strip()),
        using_global_fallback=not bool((user.smtp_host or "").strip()) and global_ok,
    )


def _resolve_effective_smtp_settings(user) -> tuple[SmtpSettings | None, bool, str | None]:
    user_host = (user.smtp_host or "").strip()
    user_password = (user.smtp_password or "").strip()
    user_port = int(user.smtp_port or 0)

    if user_host or user_password or user.smtp_port:
        if not user_host or not user_password or user_port <= 0:
            return None, False, "Your SMTP settings are incomplete"
        return (
            SmtpSettings(
                host=user_host,
                port=user_port,
                user=user.email,
                password=user_password,
                from_addr=user.email,
            ),
            False,
            None,
        )

    global_settings = get_global_smtp_settings()
    global_ok, global_error = check_smtp_config(global_settings)
    if global_ok:
        return global_settings, True, None
    return None, False, global_error


def _normalize_test_recipient(value: str, fallback: str) -> str:
    candidate = (value or "").strip().lower() or fallback.strip().lower()
    if not _EMAIL_PATTERN.match(candidate):
        raise HTTPException(status_code=400, detail="Invalid recipient email")
    return candidate


@router.post("/register", response_model=CurrentUserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> CurrentUserResponse:
    if config.SINGLE_ACCOUNT_MODE:
        raise HTTPException(status_code=409, detail="Registration is disabled in single-account mode")

    username = payload.username.strip()
    email = payload.email.strip().lower()
    display_name = (payload.display_name or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if repo.get_user_by_username(username):
        raise HTTPException(status_code=409, detail="Username already exists")
    if repo.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Email already exists")

    try:
        validate_password_strength(payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = repo.create_user(
        username=username,
        email=email,
        password_hash=hash_password(payload.password),
        display_name=display_name or username,
    )
    return _serialize_user(user)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> TokenResponse:
    if config.SINGLE_ACCOUNT_MODE:
        user = _get_single_account_user(repo)
        repo.update_user_last_login(user.id)
    else:
        try:
            user = authenticate_user(repo, payload.login, payload.password)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    return TokenResponse(
        access_token=create_access_token(user.id, user.token_version or 0),
        refresh_token=create_refresh_token(user.id, user.token_version or 0),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    payload: RefreshTokenRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> TokenResponse:
    if config.SINGLE_ACCOUNT_MODE:
        user = _get_single_account_user(repo)
        return TokenResponse(
            access_token=create_access_token(user.id, user.token_version or 0),
            refresh_token=create_refresh_token(user.id, user.token_version or 0),
        )

    try:
        token_payload = decode_token(payload.refresh_token, expected_type="refresh")
        user_id = int(token_payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    user = repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if token_payload.get("ver") != (user.token_version or 0):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    return TokenResponse(
        access_token=create_access_token(user.id, user.token_version or 0),
        refresh_token=create_refresh_token(user.id, user.token_version or 0),
    )


@router.post("/logout", response_model=AuthMutationResponse)
def logout(
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> AuthMutationResponse:
    if config.SINGLE_ACCOUNT_MODE:
        return AuthMutationResponse(success=True)

    if not repo.invalidate_user_tokens(current_user.id):
        raise HTTPException(status_code=404, detail="User not found")
    return AuthMutationResponse(success=True)


@router.get("/me", response_model=CurrentUserResponse)
def get_me(
    current_user=Depends(get_current_user),
) -> CurrentUserResponse:
    return _serialize_user(current_user)


@router.patch("/profile", response_model=CurrentUserResponse)
def update_profile(
    payload: UpdateProfileRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> CurrentUserResponse:
    user = repo.update_user_profile(
        current_user.id,
        display_name=(payload.display_name or "").strip(),
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize_user(user)


@router.post("/password", response_model=AuthMutationResponse)
def change_password(
    payload: ChangePasswordRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> AuthMutationResponse:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different")

    try:
        validate_password_strength(payload.new_password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    success = repo.update_user_password(
        current_user.id,
        password_hash=hash_password(payload.new_password),
    )
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return AuthMutationResponse(success=True)


@router.get("/smtp", response_model=UserSmtpSettingsResponse)
def get_smtp_settings(
    current_user=Depends(get_current_user),
) -> UserSmtpSettingsResponse:
    return _serialize_smtp_settings(current_user)


@router.put("/smtp", response_model=UserSmtpSettingsResponse)
def update_smtp_settings(
    payload: UpdateUserSmtpSettingsRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> UserSmtpSettingsResponse:
    smtp_host = (payload.smtp_host or "").strip()
    smtp_password = (payload.smtp_password or "").strip()
    smtp_port = int(payload.smtp_port or 0)

    if not smtp_host:
        raise HTTPException(status_code=400, detail="SMTP host is required")
    if smtp_port <= 0 or smtp_port > 65535:
        raise HTTPException(status_code=400, detail="SMTP port is invalid")
    if not smtp_password and not (current_user.smtp_password or "").strip():
        raise HTTPException(status_code=400, detail="SMTP password is required")

    user = repo.update_user_smtp_settings(
        current_user.id,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_password=smtp_password if smtp_password else None,
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize_smtp_settings(user)


@router.post("/smtp/test", response_model=SmtpTestResponse)
def test_smtp_settings(
    payload: TestSmtpSettingsRequest,
    current_user=Depends(get_current_user),
) -> SmtpTestResponse:
    settings, _, error = _resolve_effective_smtp_settings(current_user)
    if not settings:
        raise HTTPException(status_code=400, detail=error or "SMTP is not configured")

    recipient_email = _normalize_test_recipient(payload.recipient_email, current_user.email)
    service = EmailService(settings)
    success, send_error = service.send(
        recipient_email,
        "Meeting Agent SMTP Test",
        (
            "This is a test email from Meeting Agent.\n\n"
            f"Sender account: {settings.user}\n"
            f"SMTP host: {settings.host}:{settings.port}\n"
        ),
        body_html=(
            "<p>This is a test email from <strong>Meeting Agent</strong>.</p>"
            f"<p>Sender account: {settings.user}<br>SMTP host: {settings.host}:{settings.port}</p>"
        ),
        attachments=[],
        max_retries=1,
    )
    return SmtpTestResponse(
        success=success,
        recipient_email=recipient_email,
        error=send_error,
    )
