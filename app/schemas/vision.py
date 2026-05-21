from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class MacroEstimate(BaseModel):
    calories:  float = 0.0
    protein_g: float = 0.0
    carbs_g:   float = 0.0
    fats_g:    float = 0.0


class IngredientEstimate(BaseModel):
    name:       str
    quantity_g: float = 0.0
    calories:   float = 0.0
    protein_g:  float = 0.0


class TopPrediction(BaseModel):
    class_name:    str
    class_name_ar: str
    confidence:    float


class MacroFitScore(BaseModel):
    overall_score: float = 0.0
    calorie_pct:   float = 0.0
    protein_pct:   float = 0.0
    carbs_pct:     float = 0.0
    fats_pct:      float = 0.0
    budget_pct:    float = 0.0


class PersonalizationAdvice(BaseModel):
    verdict:       str = ""   # "good" | "warning" | "bad"
    message:       str = ""
    suggestion:    str = ""


class MacroWarning(BaseModel):
    type:  str    # "calories" | "fats" | "carbs" | "budget"
    pct:   float
    label: str
    level: str    # "ok" | "warning" | "danger"


class MealAnalysisResponse(BaseModel):
    meal_name:          str
    ingredients:        list[IngredientEstimate]
    estimated_macros:   MacroEstimate
    estimated_cost_egp: float = 0.0
    confidence:         float = Field(ge=0.0, le=1.0)
    analysis_notes:     Optional[str] = None
    matched_products:   list[dict] = []

    # New enhanced fields
    top3:            list[TopPrediction]          = []
    macro_fit:       Optional[MacroFitScore]      = None
    personalization: Optional[PersonalizationAdvice] = None
    warnings:        list[MacroWarning]           = []
