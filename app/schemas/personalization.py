from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── Feedback submission ───────────────────────────────────────────────────────
class FeedbackCreate(BaseModel):
    plan_id:     int
    rating:      int  = Field(..., ge=1, le=5)
    liked_items: list[int] = Field(default_factory=list)   # product_ids
    notes:       Optional[str] = None


class FeedbackResponse(FeedbackCreate):
    id:         int
    user_id:    int
    model_config = {"from_attributes": True}


# ── Saved plan ────────────────────────────────────────────────────────────────
class SavedPlanItem(BaseModel):
    product_id:  int
    product_name: str
    quantity_g:  float
    cost_egp:    float
    calories:    float
    protein_g:   float
    model_config = {"from_attributes": True}


class SavedPlanResponse(BaseModel):
    id:             int
    period:         str
    total_cost_egp: float
    total_calories: float
    total_protein_g:float
    created_at:     str
    items:          list[SavedPlanItem] = []
    model_config = {"from_attributes": True}


# ── Personalized plan request ─────────────────────────────────────────────────
class PersonalizedRequest(BaseModel):
    """
    Extends the base optimizer request with personalization hints.
    The AI layer uses past feedback to re-rank and adjust the solver output.
    """
    budget_egp:    float = Field(..., ge=10)
    calories:      float = Field(..., ge=500)
    protein_g:     float = Field(..., ge=10)
    carbs_g:       float = Field(default=0.0, ge=0)
    fats_g:        float = Field(default=0.0, ge=0)
    weekly_plan:   bool  = False
    max_items:     int   = Field(default=15, ge=3, le=50)

    # Personalization controls
    diversity_boost: float = Field(
        default=0.3, ge=0.0, le=1.0,
        description="0=pure cost-optimal, 1=maximum variety from history"
    )
    avoid_repeated:  bool  = Field(
        default=True,
        description="Avoid items rated < 3 in recent plans"
    )


# ── Personalized plan response ────────────────────────────────────────────────
class PersonalizedResponse(BaseModel):
    plan_id:           int
    status:            str
    total_cost_egp:    float
    total_calories:    float
    total_protein_g:   float
    total_carbs_g:     float
    total_fats_g:      float
    period:            str
    items:             list[SavedPlanItem]
    personalization:   dict    # metadata about how AI influenced the plan
    solve_time_ms:     float
