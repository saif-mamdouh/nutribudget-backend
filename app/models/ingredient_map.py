from sqlalchemy import (
    Column, Integer, String, Float,
    TIMESTAMP, Index, UniqueConstraint
)
from sqlalchemy.sql import func
from app.database import Base


class IngredientProductMap(Base):
    """
    Maps ingredient_key (from nutrition_facts / recipes)
    to market product SKUs.

    price_per_100g = price / unit_weight_g * 100
    This is what the optimizer uses for cost calculations.

    Example:
        ingredient_key = "rice"
        sku            = "CAR-00125"
        price_per_100g = 2.5   EGP per 100g
    """
    __tablename__ = "ingredient_product_map"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    ingredient_key   = Column(String(100), nullable=False)   # matches nutrition_facts.normalized_name
    sku              = Column(String(100), nullable=False)    # matches fresh_products.sku
    source           = Column(String(50),  nullable=True)
    product_name     = Column(String(255), nullable=True)
    price_egp        = Column(Float, default=0.0)
    unit_weight_g    = Column(Float, default=1000.0)
    price_per_100g   = Column(Float, default=0.0)           # pre-computed for optimizer speed
    created_at       = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("ingredient_key", "sku", name="uq_ing_sku"),
        Index("idx_map_ingredient_key", "ingredient_key"),
        Index("idx_map_sku",            "sku"),
    )
