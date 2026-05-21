import json
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    create_password_reset_token,
    verify_password_reset_token,
)
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserCreate, LoginRequest, TokenResponse, AccessTokenResponse,
    PasswordResetRequest, PasswordResetConfirm,
)
from app.services.email import send_password_reset_email, send_welcome_email

bearer_scheme = HTTPBearer()


# ── Internal helpers ──────────────────────────────────────────────────────────
async def _get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ── Auth operations ───────────────────────────────────────────────────────────
async def signup(payload: UserCreate, db: AsyncSession) -> User:
    if await _get_user_by_email(db, payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        daily_budget_egp=payload.daily_budget_egp,
        daily_calories=payload.daily_calories,
        daily_protein_g=payload.daily_protein_g,
        daily_carbs_g=payload.daily_carbs_g,
        daily_fats_g=payload.daily_fats_g,
        allergies=json.dumps(payload.allergies),
        dietary_prefs=payload.dietary_prefs,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Send welcome email (non-blocking — failure is logged but ignored)
    try:
        send_welcome_email(user.email, user.full_name or "")
    except Exception:
        pass

    return user


async def login(payload: LoginRequest, db: AsyncSession) -> TokenResponse:
    user = await _get_user_by_email(db, payload.email)

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
        refresh_token=create_refresh_token(user.id),
    )


async def refresh_access_token(refresh_token: str, db: AsyncSession) -> AccessTokenResponse:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = await _get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return AccessTokenResponse(access_token=create_access_token(user.id, user.email))


# ── Password reset operations ─────────────────────────────────────────────────
async def request_password_reset(payload: PasswordResetRequest, db: AsyncSession) -> dict:
    """
    Request a password reset email.
    Always returns 200 to prevent email enumeration attacks.
    """
    user = await _get_user_by_email(db, payload.email)
    if user and user.is_active:
        token = create_password_reset_token(user.email)
        try:
            send_password_reset_email(user.email, token, user.full_name or "")
        except Exception:
            pass  # Don't reveal that sending failed
    return {"status": "ok", "message": "If the email exists, a reset link has been sent"}


async def confirm_password_reset(payload: PasswordResetConfirm, db: AsyncSession) -> dict:
    """Verify reset token and update the user's password."""
    try:
        email = verify_password_reset_token(payload.token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user = await _get_user_by_email(db, email)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.hashed_password = hash_password(payload.password)
    db.add(user)
    await db.flush()
    return {"status": "ok", "message": "Password reset successfully"}


# ── FastAPI dependency: current user ──────────────────────────────────────────
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Reusable dependency — inject into any protected endpoint."""
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await _get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    return user


# ── FastAPI dependency: admin user ────────────────────────────────────────────
async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Raises 403 if the authenticated user is not an admin."""
    from fastapi import HTTPException, status
    if not getattr(current_user, 'is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user