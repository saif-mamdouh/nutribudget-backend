from sqlalchemy import (
    Column, Integer, String, Float,
    TIMESTAMP, Text, Index, UniqueConstraint
)
from sqlalchemy.sql import func
from app.database import Base


class Product(Base):
    __tablename__ = "fresh_products"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    source          = Column(String(50),  nullable=False)
    sku             = Column(String(100), nullable=False)
    category        = Column(String(100), nullable=True)
    product_name    = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=True)
    price           = Column(Float, nullable=False, default=0.0)
    unit_weight_g   = Column(Float, default=1000.0)   # ← NEW: grams per unit
    last_updated    = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("source", "sku", name="uq_source_sku"),
        Index("idx_category",        "category"),
        Index("idx_normalized_name", "normalized_name"),
    )
