from __future__ import annotations
import json
from typing import List, Literal, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

ACTIVITY_LEVELS = Literal["sedentary","light","moderate","active","very_active"]
GOALS           = Literal["weight_loss","maintenance","muscle_gain","general_health"]
GENDERS         = Literal["male","female"]


class UserBase(BaseModel):
    email:            EmailStr
    full_name:        Optional[str]   = None
    # Physical
    age:              Optional[int]   = Field(default=None, ge=10, le=100)
    weight_kg:        Optional[float] = Field(default=None, ge=30, le=300)
    height_cm:        Optional[float] = Field(default=None, ge=100, le=250)
    gender:           Optional[GENDERS] = None
    # Goals
    activity_level:   Optional[ACTIVITY_LEVELS] = None
    goal:             Optional[GOALS] = None
    # Targets
    daily_budget_egp: float = Field(default=100.0, ge=10, le=10_000)
    daily_calories:   float = Field(default=2000.0, ge=500, le=6000)
    daily_protein_g:  float = Field(default=50.0,   ge=10, le=400)
    daily_carbs_g:    float = Field(default=250.0,  ge=0,  le=1000)
    daily_fats_g:     float = Field(default=65.0,   ge=0,  le=300)
    # Restrictions
    allergies:        List[str] = Field(default_factory=list)
    dietary_prefs:    Optional[str] = None
    forbidden_foods:  List[str] = Field(default_factory=list)


class UserCreate(UserBase):
    password:         str = Field(min_length=8)
    password_confirm: str

    @model_validator(mode="after")
    def passwords_match(self) -> "UserCreate":
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self

    @field_validator("allergies", "forbidden_foods", mode="before")
    @classmethod
    def parse_list(cls, v):
        if isinstance(v, str):
            try: return json.loads(v)
            except: return []
        return v or []


class UserUpdate(BaseModel):
    full_name:        Optional[str]   = None
    age:              Optional[int]   = Field(default=None, ge=10, le=100)
    weight_kg:        Optional[float] = Field(default=None, ge=30, le=300)
    height_cm:        Optional[float] = Field(default=None, ge=100, le=250)
    gender:           Optional[GENDERS] = None
    activity_level:   Optional[ACTIVITY_LEVELS] = None
    goal:             Optional[GOALS] = None
    daily_budget_egp: Optional[float] = Field(default=None, ge=10, le=10_000)
    daily_calories:   Optional[float] = Field(default=None, ge=500, le=6000)
    daily_protein_g:  Optional[float] = Field(default=None, ge=10, le=400)
    daily_carbs_g:    Optional[float] = Field(default=None, ge=0,  le=1000)
    daily_fats_g:     Optional[float] = Field(default=None, ge=0,  le=300)
    allergies:        Optional[List[str]] = None
    dietary_prefs:    Optional[str]       = None
    forbidden_foods:  Optional[List[str]] = None


class UserResponse(UserBase):
    id:          int
    is_active:   bool
    is_verified: bool
    is_admin:    bool = False

    model_config = {"from_attributes": True}

    @field_validator("allergies", "forbidden_foods", mode="before")
    @classmethod
    def parse_list_from_db(cls, v):
        if isinstance(v, str):
            try: return json.loads(v)
            except: return []
        return v or []


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"



# ── Password Reset Schemas ────────────────────────────────────────────────────
class PasswordResetRequest(BaseModel):
    """Step 1: User requests password reset by email."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Step 2: User submits new password + token from email."""
    token:            str
    password:         str = Field(min_length=8)
    password_confirm: str

    @model_validator(mode="after")
    def passwords_match(self) -> "PasswordResetConfirm":
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self