from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ── Single product ─────────────────────────────────────────────────────────────
class ProductBase(BaseModel):
    source: str
    sku: str
    category: Optional[str] = None
    product_name: str
    price: float = Field(ge=0)
    unit_weight_g: float = Field(default=1000.0, ge=1)


class ProductCreate(ProductBase):
    pass


class ProductResponse(ProductBase):
    id: int
    normalized_name: Optional[str] = None

    model_config = {"from_attributes": True}


# ── CSV upload response ────────────────────────────────────────────────────────
class UploadSummary(BaseModel):
    total_rows: int
    inserted: int
    updated: int
    skipped: int        # rows with 0 price or missing SKU
    errors: int
    message: str


# ── Nutrition schemas ──────────────────────────────────────────────────────────
class NutritionCreate(BaseModel):
    normalized_name: str
    display_name: Optional[str] = None
    calories_per_100g: float = Field(ge=0, default=0)
    protein_g: float         = Field(ge=0, default=0)
    carbs_g: float           = Field(ge=0, default=0)
    fats_g: float            = Field(ge=0, default=0)
    fiber_g: float           = Field(ge=0, default=0)
    data_source: str         = "manual"


class NutritionResponse(NutritionCreate):
    id: int
    fiber_g: Optional[float]   = 0.0
    data_source: Optional[str] = "manual"
    model_config = {"from_attributes": True}


# ── Mapping response ───────────────────────────────────────────────────────────
class MappingResponse(BaseModel):
    product_id: int
    nutrition_id: int
    confidence: float
    match_method: str

    model_config = {"from_attributes": True}