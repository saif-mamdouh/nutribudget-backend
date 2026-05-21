from sqlalchemy import (
    Column, Integer, Float, String, Boolean,
    ForeignKey, TIMESTAMP, Text, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class MealPlan(Base):
    """Stores a generated meal plan for a user."""
    __tablename__ = "meal_plans"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    period         = Column(String(10), default="daily")   # daily | weekly
    total_cost_egp = Column(Float, default=0.0)
    total_calories = Column(Float, default=0.0)
    total_protein_g= Column(Float, default=0.0)
    total_carbs_g  = Column(Float, default=0.0)
    total_fats_g   = Column(Float, default=0.0)
    solver_status  = Column(String(20), default="optimal")
    meal_names     = Column(Text, nullable=True)   # JSON list: ["كشري","ملوخية",...]
    created_at     = Column(TIMESTAMP, server_default=func.now())

    items    = relationship("MealPlanItem", backref="plan", cascade="all, delete-orphan")
    feedback = relationship("UserFeedback",  backref="plan", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_plan_user", "user_id"),
        Index("idx_plan_created", "created_at"),
    )


class MealPlanItem(Base):
    """Individual food item in a meal plan."""
    __tablename__ = "meal_plan_items"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    plan_id      = Column(Integer, ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False)
    product_id   = Column(Integer, ForeignKey("fresh_products.id"), nullable=False)
    quantity_g   = Column(Float, default=0.0)
    cost_egp     = Column(Float, default=0.0)
    calories     = Column(Float, default=0.0)
    protein_g    = Column(Float, default=0.0)
    carbs_g      = Column(Float, default=0.0)
    fats_g       = Column(Float, default=0.0)

    product = relationship("Product", backref="plan_items")


class UserFeedback(Base):
    """
    User ratings on generated plans — feeds the personalization layer.
    rating: 1 (dislike) to 5 (love it)
    """
    __tablename__ = "user_feedback"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id     = Column(Integer, ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False)
    rating      = Column(Integer, nullable=False)      # 1–5
    liked_items = Column(Text, nullable=True)          # JSON list of product_ids user liked
    notes       = Column(Text, nullable=True)
    created_at  = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("idx_feedback_user", "user_id"),
    )
