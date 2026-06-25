from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_current_user, get_meeting_repository
from api.schemas.auth import (
    AuthMutationResponse,
    CurrentUserResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
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
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=CurrentUserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> CurrentUserResponse:
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
    return CurrentUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name or user.username,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> TokenResponse:
    try:
        user = authenticate_user(repo, payload.login, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    payload: RefreshTokenRequest,
    repo: MeetingRepository = Depends(get_meeting_repository),
) -> TokenResponse:
    try:
        token_payload = decode_token(payload.refresh_token, expected_type="refresh")
        user_id = int(token_payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    user = repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/logout", response_model=AuthMutationResponse)
def logout() -> AuthMutationResponse:
    return AuthMutationResponse(success=True)


@router.get("/me", response_model=CurrentUserResponse)
def get_me(
    current_user=Depends(get_current_user),
) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        display_name=current_user.display_name or current_user.username,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )
