"""
routers/profile.py
────────────────────
Exposes the 3-layer pipeline as REST endpoints.

POST /profile/parse-text          Layer 1 only  (NLP)
POST /profile/calculate-macros    Layer 2 only  (ML)
POST /profile/full-pipeline       L1 + L2       (NLP → ML)
GET  /profile/my-targets          Returns saved targets
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.services.auth import get_current_user
from app.models.user import User
from app.schemas.profile import (
    NLPTextRequest, ManualProfileRequest,
    ParsedProfile, MacroTargets, FullPipelineResponse,
)
from app.services.nlp_parser       import parse_user_text
from app.services.macro_calculator import (
    calculate_from_manual, calculate_from_parsed, calculate_macros
)

router = APIRouter(prefix="/profile", tags=["Profile & Macros"])


# ── POST /profile/parse-text ──────────────────────────────────────────────────
@router.post("/parse-text", response_model=ParsedProfile)
async def parse_text(
    req: NLPTextRequest,
    _: User = Depends(get_current_user),
):
    """
    Layer 1 — NLP.
    Send Arabic or English text, get structured profile back.
    Example: "أنا 28 سنة، 90 كيلو، عايز أنزل وزن"
    """
    return await parse_user_text(req.text)


# ── POST /profile/calculate-macros ───────────────────────────────────────────
@router.post("/calculate-macros", response_model=MacroTargets)
async def calculate_macros_endpoint(
    req: ManualProfileRequest,
    _: User = Depends(get_current_user),
):
    """
    Layer 2 — Macro Calculator (Mifflin-St Jeor + goal regression).
    Manual input: age, weight, height, gender, activity, goal.
    """
    return calculate_from_manual(req)


# ── POST /profile/full-pipeline ───────────────────────────────────────────────
@router.post("/full-pipeline", response_model=FullPipelineResponse)
async def full_pipeline(
    req: NLPTextRequest,
    _: User = Depends(get_current_user),
):
    """
    Layer 1 → Layer 2.
    Text in → macro targets out.
    If NLP confidence < 0.5, returns partial results with a warning.
    """
    # Layer 1: NLP
    profile = await parse_user_text(req.text)

    # Check if we got enough info
    missing = []
    if not profile.age:        missing.append("age (عمر)")
    if not profile.weight_kg:  missing.append("weight (وزن)")
    if not profile.height_cm:  missing.append("height (طول)")

    if len(missing) >= 2:
        return FullPipelineResponse(
            parsed_profile=profile,
            nlp_used=True,
            macro_targets=MacroTargets(
                calories=0, protein_g=0, carbs_g=0, fats_g=0, fiber_g=0,
                budget_egp=0, bmr=0, tdee=0, goal="general_health",
                deficit_surplus=0, activity_multiplier=1.55,
                weekly_calories=0, weekly_protein_g=0, weekly_budget_egp=0,
                milp_ready={},
            ),
            suggested_plan_type="daily",
            message=f"Couldn't extract: {', '.join(missing)}. Please provide manually.",
        )

    # Layer 2: Macros
    macros = calculate_from_parsed(profile)

    # Determine plan type suggestion
    plan_type = "daily"
    if profile.goal in ("weight_loss", "muscle_gain"):
        plan_type = "weekly"   # weekly plan better for fitness goals

    goal_msg = {
        "weight_loss":    "هدفك إنقاص الوزن — كالوري أقل من الـ TDEE بـ 500 kcal.",
        "muscle_gain":    "هدفك بناء عضل — كالوري أكتر من الـ TDEE بـ 300 kcal.",
        "maintenance":    "هدفك ثبات الوزن — كالوري يساوي الـ TDEE.",
        "general_health": "هدفك صحة عامة — كالوري أقل بسيط من الـ TDEE.",
    }.get(profile.goal or "general_health", "")

    return FullPipelineResponse(
        parsed_profile=profile,
        nlp_used=True,
        macro_targets=macros,
        suggested_plan_type=plan_type,
        message=f"✅ تم حساب الـ targets! {goal_msg}",
    )


# ── POST /profile/save-targets ────────────────────────────────────────────────
@router.post("/save-targets")
async def save_targets(
    req: ManualProfileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save calculated targets to user profile."""
    macros = calculate_from_manual(req)

    await db.execute(text("""
        UPDATE users SET
            daily_calories   = :cal,
            daily_protein_g  = :prot,
            daily_carbs_g    = :carbs,
            daily_fats_g     = :fats,
            daily_budget_egp = :budget
        WHERE id = :uid
    """), {
        "cal":    macros.calories,
        "prot":   macros.protein_g,
        "carbs":  macros.carbs_g,
        "fats":   macros.fats_g,
        "budget": macros.budget_egp,
        "uid":    current_user.id,
    })
    await db.commit()

    return {
        "status": "saved",
        "message": "Targets saved to your profile",
        "macros": macros,
    }
