from sqlalchemy import (
    Column, Integer, Float, String, ForeignKey,
    TIMESTAMP, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ProductNutritionMap(Base):
    """
    Links a market product to its best nutrition record.
    confidence_score >= 0.75  → used by optimizer
    confidence_score <  0.75  → flagged for manual review
    """
    __tablename__ = "product_nutrition_map"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    product_id       = Column(Integer, ForeignKey("fresh_products.id", ondelete="CASCADE"), nullable=False)
    nutrition_id     = Column(Integer, ForeignKey("nutrition_facts.id", ondelete="CASCADE"), nullable=False)
    confidence_score = Column(Float, default=0.0)
    match_method     = Column(String(50), default="fuzzy")   # fuzzy | embedding | manual
    created_at       = Column(TIMESTAMP, server_default=func.now())

    product   = relationship("Product",       backref="nutrition_maps")
    nutrition = relationship("NutritionFact", backref="product_maps")

    __table_args__ = (
        UniqueConstraint("product_id", "nutrition_id", name="uq_product_nutrition"),
        Index("idx_map_confidence", "confidence_score"),
    )
