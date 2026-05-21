from datetime import datetime, timedelta, timezone
from typing import Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ── Password hashing ──────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────
TokenType = Literal["access", "refresh"]


def _create_token(data: dict, token_type: TokenType, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload.update({
        "type": token_type,
        "exp": datetime.now(timezone.utc) + expires_delta,
        "iat": datetime.now(timezone.utc),
    })
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: int, email: str) -> str:
    return _create_token(
        data={"sub": str(user_id), "email": email},
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        data={"sub": str(user_id)},
        token_type="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType) -> dict:
    """
    Decodes and validates a JWT.
    Raises JWTError on any failure (expired, wrong type, bad signature).
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != expected_type:
            raise JWTError("Wrong token type")
        return payload
    except JWTError:
        raise



# ── Password Reset Tokens ─────────────────────────────────────────────────────
def create_password_reset_token(email: str) -> str:
    """Create a short-lived token for password reset (default: 30 min)."""
    payload = {
        "sub":   email,
        "type":  "password_reset",
        "exp":   datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
        "iat":   datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_password_reset_token(token: str) -> str:
    """
    Verify a password reset token and return the email.
    Raises JWTError if invalid or expired.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "password_reset":
            raise JWTError("Wrong token type")
        email = payload.get("sub")
        if not email:
            raise JWTError("Missing email in token")
        return email
    except JWTError:
        raise