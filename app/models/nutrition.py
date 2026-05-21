from sqlalchemy import (
    Column, Integer, String, Float,
    TIMESTAMP, Index
)
from sqlalchemy.sql import func
from app.database import Base


class NutritionFact(Base):
    __tablename__ = "nutrition_facts"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    normalized_name  = Column(String(255), unique=True, nullable=False)  # lookup key
    display_name     = Column(String(255), nullable=True)

    # ── Macros per 100g ───────────────────────────────────────────────────
    calories_per_100g = Column(Float, default=0.0)
    protein_g         = Column(Float, default=0.0)
    carbs_g           = Column(Float, default=0.0)
    fats_g            = Column(Float, default=0.0)
    fiber_g           = Column(Float, default=0.0)

    # ── Meta ──────────────────────────────────────────────────────────────
    data_source   = Column(String(100), default="manual")   # manual | usda | openfoodfacts
    created_at    = Column(TIMESTAMP, server_default=func.now())
    updated_at    = Column(TIMESTAMP, onupdate=func.now())

    __table_args__ = (
        Index("idx_nutrition_name", "normalized_name"),
    )
