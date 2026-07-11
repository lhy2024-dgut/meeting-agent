from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

import config


class AuthError(ValueError):
    pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters")
    if password.lower() == password or password.upper() == password:
        raise AuthError("Password must contain both upper and lower case letters")
    if not any(char.isdigit() for char in password):
        raise AuthError("Password must contain at least one digit")


def _build_token(user_id: int, token_type: str, expire_days: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=expire_days)).timestamp()),
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _build_token(user_id, "access", config.JWT_EXPIRE_DAYS)


def create_refresh_token(user_id: int) -> str:
    return _build_token(user_id, "refresh", config.REFRESH_TOKEN_EXPIRE_DAYS)


def decode_token(token: str, expected_type: str | None = None) -> dict:
    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid token") from exc

    if expected_type and payload.get("type") != expected_type:
        raise AuthError("Unexpected token type")
    return payload


def authenticate_user(repo, login: str, password: str):
    user = repo.get_user_by_login(login.strip())
    if not user or not verify_password(password, user.password_hash):
        raise AuthError("Invalid username/email or password")
    repo.update_user_last_login(user.id)
    return user
