from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import (
    UserCreate, UserResponse, LoginRequest, TokenResponse, RefreshRequest,
    AccessTokenResponse, PasswordResetRequest, PasswordResetConfirm,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=UserResponse, status_code=201)
async def signup(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Register a new user. Sends a welcome email.
    Returns the created user profile (no password).
    """
    user = await auth_service.signup(payload, db)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate and receive access + refresh tokens."""
    return await auth_service.login(payload, db)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a new access token."""
    return await auth_service.refresh_access_token(payload.refresh_token, db)


@router.post("/forgot-password")
async def forgot_password(payload: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    """
    Request a password reset email.
    Always returns 200 — never reveals whether the email exists.
    """
    return await auth_service.request_password_reset(payload, db)


@router.post("/reset-password")
async def reset_password(payload: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    """Reset password using token from email."""
    return await auth_service.confirm_password_reset(payload, db)