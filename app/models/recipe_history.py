"""
models/recipe_history.py
─────────────────────────
Tracks user interactions with recipes for personalization.

Used by: Ge et al. (2015) — Health-aware Food Recommendation pipeline
Interaction types:
  "viewed"   — user saw this recipe in results
  "liked"    — user explicitly liked/saved
  "disliked" — user dismissed/skipped
  "planned"  — recipe was in an optimized plan
"""
from sqlalchemy import Column, Integer, String, ForeignKey, TIMESTAMP, Index
from sqlalchemy.sql import func
from app.database import Base


class RecipeHistory(Base):
    __tablename__ = "recipe_history"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipe_id        = Column(Integer, ForeignKey("recipes.recipe_id"), nullable=False)
    recipe_name      = Column(String(255))          # denormalized for speed
    interaction_type = Column(String(20), default="viewed")  # viewed/liked/disliked/planned
    created_at       = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("idx_history_user",   "user_id"),
        Index("idx_history_recipe", "recipe_id"),
        Index("idx_history_type",   "user_id", "interaction_type"),
    )
