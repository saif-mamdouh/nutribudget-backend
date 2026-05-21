"""
schemas/profile.py
───────────────────
Schemas for the 3-layer pipeline:
  Layer 1: NLP  → ParsedProfile
  Layer 2: ML   → MacroTargets
  Layer 3: MILP → uses existing MealPlanRequest
"""
from __future__ import annotations
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ── Layer 1: NLP Input ────────────────────────────────────────────────────────

class NLPTextRequest(BaseModel):
    """Raw text from user — Arabic or English."""
    text: str = Field(
        ..., min_length=3, max_length=1000,
        description="Free-form text describing user's profile and goal",
        examples=[
            "أنا عندي 25 سنة، وزني 85 كيلو، طولي 175، بمشي نص ساعة في اليوم، عايز أنزل وزن",
            "Male, 30 years old, 80kg, 178cm, gym 4 times a week, goal: muscle gain",
        ]
    )
    language: Optional[Literal["ar", "en", "auto"]] = "auto"


class ParsedProfile(BaseModel):
    """Structured profile extracted by NLP layer."""
    age:            Optional[int]   = None
    weight_kg:      Optional[float] = None
    height_cm:      Optional[float] = None
    gender:         Optional[Literal["male", "female"]] = None
    activity_level: Optional[Literal[
        "sedentary",    # مكتبي / لا يتحرك
        "light",        # نشاط خفيف 1-3 أيام
        "moderate",     # نشاط متوسط 3-5 أيام
        "active",       # نشاط مرتفع 6-7 أيام
        "very_active",  # رياضي / شغل بدني
    ]] = "moderate"
    goal: Optional[Literal[
        "weight_loss",    # إنقاص وزن
        "maintenance",    # ثبات وزن
        "muscle_gain",    # بناء عضل
        "general_health", # صحة عامة
    ]] = "general_health"
    budget_egp:     Optional[float] = None
    notes:          Optional[str]   = None
    confidence:     float = Field(default=0.8, ge=0, le=1,
                                  description="NLP confidence in extraction")
    raw_text:       Optional[str]   = None


# ── Layer 2: Manual Input (fallback when NLP is skipped) ─────────────────────

class ManualProfileRequest(BaseModel):
    """Direct manual input — same fields as ParsedProfile but all required."""
    age:            int   = Field(..., ge=10, le=100)
    weight_kg:      float = Field(..., ge=30, le=300)
    height_cm:      float = Field(..., ge=100, le=250)
    gender:         Literal["male", "female"]
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"]
    goal:           Literal["weight_loss", "maintenance", "muscle_gain", "general_health"]
    budget_egp:     float = Field(default=200, ge=20)


# ── Layer 2: Output ───────────────────────────────────────────────────────────

class MacroTargets(BaseModel):
    """
    Calculated daily macro targets.
    Based on: Mifflin-St Jeor BMR + goal adjustments.
    """
    # Core macros
    calories:    float  # kcal/day
    protein_g:   float  # g/day
    carbs_g:     float  # g/day
    fats_g:      float  # g/day
    fiber_g:     float  # g/day

    # Budget (daily)
    budget_egp:  float

    # Metadata
    bmr:         float          # Basal Metabolic Rate
    tdee:        float          # Total Daily Energy Expenditure
    goal:        str
    deficit_surplus: float      # calories vs TDEE
    activity_multiplier: float
    bmi:         Optional[float] = None
    bmi_category:Optional[str]  = None

    # Weekly equivalents
    weekly_calories:  float
    weekly_protein_g: float
    weekly_budget_egp:float

    # Ready-to-use for MILP
    milp_ready: dict            # directly passable to MealPlanRequest


class FullPipelineResponse(BaseModel):
    """Complete response from all 3 layers."""
    # Layer 1 result
    parsed_profile:  Optional[ParsedProfile]  = None
    nlp_used:        bool = False

    # Layer 2 result
    macro_targets:   MacroTargets

    # Layer 3 hint (user confirms before running MILP)
    suggested_plan_type: Literal["single", "daily", "weekly"] = "daily"
    message:         str
