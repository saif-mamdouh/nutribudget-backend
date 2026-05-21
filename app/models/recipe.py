from sqlalchemy import (
    Column, Integer, String, Text, TIMESTAMP, Index
)
from sqlalchemy.sql import func
from app.database import Base


class Recipe(Base):
    """
    Stores Egyptian meal recipes.
    ingredients_json format: [{"name": "rice", "weight_g": 100}, ...]
    ingredient names MUST match ingredient_key in NutritionFact.
    """
    __tablename__ = "recipes"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id        = Column(Integer, unique=True, nullable=False)   # from dataset
    recipe_name      = Column(String(255), nullable=False)
    meal_type        = Column(String(50),  nullable=True)    # فطار / غداء / عشاء
    ingredients_json = Column(Text, nullable=False)           # JSON string
    instructions     = Column(Text, nullable=True)
    prep_time        = Column(Integer, default=0)             # minutes
    created_at       = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("idx_recipe_meal_type", "meal_type"),
    )
