from __future__ import annotations
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ── Ingredient-level (existing) ───────────────────────────────────────────────
class OptimizeRequest(BaseModel):
    budget_egp:   float = Field(..., ge=10, le=10_000)
    calories:     float = Field(..., ge=500, le=6_000)
    protein_g:    float = Field(..., ge=10, le=400)
    carbs_g:      float = Field(default=0.0, ge=0)
    fats_g:       float = Field(default=0.0, ge=0)
    source:       Optional[str]       = None
    categories:   Optional[list[str]] = None
    max_items:    int   = Field(default=15, ge=3, le=50)
    min_quantity: float = Field(default=100, ge=10)
    max_quantity: float = Field(default=1000, le=5000)
    weekly_plan:  bool  = Field(default=False)


class OptimizedItem(BaseModel):
    product_id:     str
    product_name:   str
    source:         str
    category:       Optional[str]
    ingredient_key: Optional[str] = None   # for category grouping in frontend
    unit_weight_g:  float         = 0.0    # for pack size calculation
    quantity_g:     float
    price_per_100g: float
    cost_egp:       float
    calories:       float
    protein_g:      float
    carbs_g:        float
    fats_g:         float


class OptimizeResponse(BaseModel):
    status:          str
    total_cost_egp:  float
    total_calories:  float
    total_protein_g: float
    total_carbs_g:   float
    total_fats_g:    float
    items:           list[OptimizedItem]
    solve_time_ms:   float
    solver_message:  str
    period:          str
    budget_used_pct: float
    calories_met:    bool
    protein_met:     bool


# ── NEW: Meal-level plan ──────────────────────────────────────────────────────

class MealPlanRequest(BaseModel):
    """
    Meal-level MILP: selects real Egyptian recipes from the dataset.

    plan_type:
      "single"  → 1 meal  (user picks meal_type if desired)
      "daily"   → 3 meals (فطار + غداء + عشاء)
      "weekly"  → 21 meals (3/day × 7 days)
    """
    budget_egp:  float = Field(..., ge=10,  le=10_000)
    calories:    float = Field(..., ge=500, le=50_000)
    protein_g:   float = Field(..., ge=10,  le=3_000)

    plan_type:   Literal["single", "daily", "weekly"] = "daily"
    meal_type:   Optional[Literal["فطار", "غداء", "عشاء"]] = None  # single only
    max_repeat:  int  = Field(default=2, ge=1, le=7)
    source:      Optional[str] = None


class PlannedMeal(BaseModel):
    recipe_id:   int
    recipe_name: str
    meal_type:   Optional[str]
    day:         Optional[int]   # 1-7 weekly, None otherwise
    slot:        Optional[str]   # "breakfast" / "lunch" / "dinner"
    ingredients: list[dict]
    cost_egp:    float
    calories:    float
    protein_g:   float
    carbs_g:     float
    fats_g:      float
    prep_time:   int


class MealPlanResponse(BaseModel):
    status:          str
    plan_type:       str
    plan_id:         Optional[int] = None   # set after DB save
    total_cost_egp:  float
    total_calories:  float
    total_protein_g: float
    total_carbs_g:   float
    total_fats_g:    float
    total_meals:     int
    meals:           list[PlannedMeal]
    solve_time_ms:   float
    solver_message:  str
    budget_used_pct: float
    calories_met:    bool
    protein_met:     bool
    days:            Optional[dict] = None   # weekly breakdown
