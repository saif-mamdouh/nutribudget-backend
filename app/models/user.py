from sqlalchemy import (
    Boolean, Column, Float, Integer,
    String, Text, TIMESTAMP, Index, SmallInteger
)
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    email            = Column(String(255), unique=True, nullable=False)
    full_name        = Column(String(255), nullable=True)
    hashed_password  = Column(String(255), nullable=False)

    # ── Physical profile (used by Mifflin-St Jeor BMR) ────────────────────
    age              = Column(SmallInteger, nullable=True)
    weight_kg        = Column(Float, nullable=True)
    height_cm        = Column(Float, nullable=True)
    gender           = Column(String(10), nullable=True)    # male / female

    # ── Goals & activity (used by macro calculator) ───────────────────────
    activity_level   = Column(String(20), nullable=True)   # sedentary/light/moderate/active/very_active
    goal             = Column(String(30), nullable=True)   # weight_loss/maintenance/muscle_gain/general_health

    # ── Nutrition targets (auto-filled by Smart Profile) ──────────────────
    daily_budget_egp = Column(Float, default=100.0)
    daily_calories   = Column(Float, default=2000.0)
    daily_protein_g  = Column(Float, default=50.0)
    daily_carbs_g    = Column(Float, default=250.0)
    daily_fats_g     = Column(Float, default=65.0)

    # ── Preferences / restrictions ─────────────────────────────────────────
    allergies        = Column(Text, nullable=True)    # JSON list: ["lactose", "gluten"]
    dietary_prefs    = Column(String(100), nullable=True)  # vegetarian / vegan / halal
    forbidden_foods  = Column(Text, nullable=True)    # JSON list: ["liver", "fish"]

    # ── Account state ──────────────────────────────────────────────────────
    is_active        = Column(Boolean, default=True)
    is_verified      = Column(Boolean, default=False)
    is_admin         = Column(Boolean, default=False)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, onupdate=func.now())

    __table_args__ = (
        Index("idx_email", "email"),
        Index("idx_is_active", "is_active"),
    )
