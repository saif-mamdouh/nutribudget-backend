"""
services/macro_calculator.py
──────────────────────────────
Layer 2: ML-based Macro Calculation

Scientific basis:
  - Mifflin & St Jeor (1990): BMR equation
    Male:   BMR = 10×W + 6.25×H - 5×A + 5
    Female: BMR = 10×W + 6.25×H - 5×A - 161

  - Activity multipliers (Harris-Benedict):
    sedentary:   1.2  (desk job, no exercise)
    light:       1.375 (1-3 days/week)
    moderate:    1.55  (3-5 days/week)
    active:      1.725 (6-7 days/week)
    very_active: 1.9   (twice/day or physical job)

  - Goal-based adjustments:
    weight_loss:    TDEE - 500 kcal (0.5kg/week deficit)
    muscle_gain:    TDEE + 300 kcal (lean bulk)
    maintenance:    TDEE
    general_health: TDEE - 100 (mild deficit for general health)

  - Macro ratios per goal (Min et al., 2019):
    weight_loss:    P=35%, C=40%, F=25%
    muscle_gain:    P=35%, C=45%, F=20%
    maintenance:    P=25%, C=50%, F=25%
    general_health: P=20%, C=55%, F=25%

Reference:
  Mifflin MD, St Jeor ST, et al. (1990). "A new predictive equation for
  resting energy expenditure in healthy individuals." AJCN, 51(2), 241-247.
"""

import math
from app.schemas.profile import ManualProfileRequest, ParsedProfile, MacroTargets

# ── Constants ─────────────────────────────────────────────────────────────────

ACTIVITY_MULTIPLIERS = {
    "sedentary":    1.200,
    "light":        1.375,
    "moderate":     1.550,
    "active":       1.725,
    "very_active":  1.900,
}

# (protein_pct, carbs_pct, fats_pct) of total calories
MACRO_RATIOS = {
    "weight_loss":    (0.35, 0.40, 0.25),
    "muscle_gain":    (0.35, 0.45, 0.20),
    "maintenance":    (0.25, 0.50, 0.25),
    "general_health": (0.20, 0.55, 0.25),
}

# Calorie deficit/surplus per goal (kcal)
GOAL_ADJUSTMENTS = {
    "weight_loss":    -500,
    "muscle_gain":    +300,
    "maintenance":      0,
    "general_health": -100,
}

# Egyptian market avg cost per macro gram (EGP, rough estimate)
# Used to suggest budget if user didn't provide one
COST_PER_KCAL_EGP = 0.10   # ~0.1 EGP per kcal → 2000 kcal = 200 EGP/day

GOAL_LABELS = {
    "weight_loss":    "إنقاص وزن (Weight Loss)",
    "muscle_gain":    "بناء عضل (Muscle Gain)",
    "maintenance":    "ثبات وزن (Maintenance)",
    "general_health": "صحة عامة (General Health)",
}


# ── BMR Calculation ───────────────────────────────────────────────────────────

def calculate_bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> float:
    """
    Mifflin-St Jeor equation (1990).
    Most accurate for non-athletic adults.
    """
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if gender == "male" else base - 161


def calculate_bmi(weight_kg: float, height_cm: float) -> tuple[float, str]:
    h_m  = height_cm / 100
    bmi  = weight_kg / (h_m ** 2)
    if bmi < 18.5:
        category = "Underweight (نقص وزن)"
    elif bmi < 25:
        category = "Normal (وزن طبيعي)"
    elif bmi < 30:
        category = "Overweight (زيادة وزن)"
    else:
        category = "Obese (سمنة)"
    return round(bmi, 1), category


# ── Main calculation ──────────────────────────────────────────────────────────

def calculate_macros(
    age:            int,
    weight_kg:      float,
    height_cm:      float,
    gender:         str,
    activity_level: str,
    goal:           str,
    budget_egp:     float = 0.0,
) -> MacroTargets:
    """
    Full macro calculation pipeline.

    Layer 2 implementation:
      Step 1: BMR  (Mifflin-St Jeor)
      Step 2: TDEE (BMR × activity multiplier)
      Step 3: Target calories (TDEE ± goal adjustment)
      Step 4: Macro split (protein/carbs/fats) per goal ratios
      Step 5: Budget estimation if not provided
    """

    # Step 1: BMR
    bmr = calculate_bmr(weight_kg, height_cm, age, gender)

    # Step 2: TDEE
    mult = ACTIVITY_MULTIPLIERS.get(activity_level, 1.55)
    tdee = bmr * mult

    # Step 3: Target calories
    adjustment     = GOAL_ADJUSTMENTS.get(goal, 0)
    target_cal     = max(1200, tdee + adjustment)   # never below 1200 kcal

    # Step 4: Macro split (calories → grams)
    p_pct, c_pct, f_pct = MACRO_RATIOS.get(goal, (0.25, 0.50, 0.25))
    protein_cal = target_cal * p_pct
    carbs_cal   = target_cal * c_pct
    fats_cal    = target_cal * f_pct

    protein_g = protein_cal / 4   # 1g protein = 4 kcal
    carbs_g   = carbs_cal   / 4   # 1g carbs   = 4 kcal
    fats_g    = fats_cal    / 9   # 1g fat      = 9 kcal

    # Minimum protein floor (1.6g/kg for active, 0.8g/kg sedentary)
    min_protein_per_kg = {
        "sedentary":   0.8,
        "light":       1.2,
        "moderate":    1.6,
        "active":      2.0,
        "very_active": 2.2,
    }.get(activity_level, 1.6)
    protein_g = max(protein_g, weight_kg * min_protein_per_kg)

    # Fiber recommendation
    fiber_g = 25 if gender == "female" else 38

    # Step 5: Budget
    if not budget_egp or budget_egp < 20:
        budget_egp = round(target_cal * COST_PER_KCAL_EGP, 0)

    # BMI
    bmi, bmi_cat = calculate_bmi(weight_kg, height_cm)

    # Weekly
    weekly_cal     = target_cal * 7
    weekly_prot    = protein_g  * 7
    weekly_budget  = budget_egp * 7

    # MILP-ready dict (for direct use in MealPlanRequest)
    milp_ready = {
        "budget_egp": round(budget_egp, 0),
        "calories":   round(target_cal, 0),
        "protein_g":  round(protein_g,  1),
        "plan_type":  "daily",
        "max_repeat": 2,
    }

    return MacroTargets(
        calories=round(target_cal, 1),
        protein_g=round(protein_g, 1),
        carbs_g=round(carbs_g, 1),
        fats_g=round(fats_g, 1),
        fiber_g=fiber_g,
        budget_egp=round(budget_egp, 0),
        bmr=round(bmr, 1),
        tdee=round(tdee, 1),
        goal=goal,
        deficit_surplus=round(adjustment, 0),
        activity_multiplier=mult,
        bmi=bmi,
        bmi_category=bmi_cat,
        weekly_calories=round(weekly_cal, 0),
        weekly_protein_g=round(weekly_prot, 1),
        weekly_budget_egp=round(weekly_budget, 0),
        milp_ready=milp_ready,
    )


def calculate_from_manual(req: ManualProfileRequest) -> MacroTargets:
    return calculate_macros(
        age=req.age, weight_kg=req.weight_kg,
        height_cm=req.height_cm, gender=req.gender,
        activity_level=req.activity_level, goal=req.goal,
        budget_egp=req.budget_egp,
    )


def calculate_from_parsed(profile: ParsedProfile) -> MacroTargets:
    """Calculate from NLP-parsed profile with fallback defaults."""
    return calculate_macros(
        age=profile.age or 25,
        weight_kg=profile.weight_kg or 70,
        height_cm=profile.height_cm or 170,
        gender=profile.gender or "male",
        activity_level=profile.activity_level or "moderate",
        goal=profile.goal or "general_health",
        budget_egp=profile.budget_egp or 0,
    )
