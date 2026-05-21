"""
services/personalization.py
─────────────────────────────
History-Based Recipe Recommendations (Ge et al. 2015) — Enhanced

Algorithm:
  1. Load user's liked/planned recipe history
  2. Build taste profile = average MiniLM embedding of liked recipes
  3. Score all 300 recipes by cosine similarity to taste profile
  4. Apply FOUR enhancements:
       A. Macro fit score   — how well does the recipe hit the user's targets?
       B. Why recommended   — detailed explanation with contributing factors
       C. Dislike feedback  — instant score penalty when user dislikes
       D. Diversity inject  — guarantee variety across meal types
  5. Return top-k with explanations and macro fit details

Cold Start (< 3 interactions):
  Fall back to best protein/cost ratio ranking

Paper: Ge et al. (2015) — Health-aware Food Recommendation, IEEE ICDM

Enhancements over base paper:
  - Nutritional constraint integration (macro fit scoring)
  - Diversity-aware re-ranking (MMR-inspired)
  - Explainability layer (multi-factor reason strings)
  - Real-time preference updates via dislike penalty
"""

import logging
from typing import Optional
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("nutribudget.personalization")

COLD_START_THRESHOLD = 3

# ── Recipe name embeddings cache ──────────────────────────────────────────────
# Cached once at startup, invalidated only if recipe list changes (rare).
# This is the main bottleneck — encoding 332 recipes takes 4-5 seconds.
_RECIPE_VECS_CACHE   = None
_RECIPE_NAMES_CACHE  = None  # to detect if recipes changed

# ── Enhancement A: Composite score weights ───────────────────────────────────
W_TASTE  = 0.65   # MiniLM cosine similarity
W_MACRO  = 0.25   # Macro proximity to user targets
W_BUDGET = 0.10   # Budget fit

DIVERSITY_CAP = 2  # max 2 per meal_type (was 3 — more variety)


# ── Macro & budget helpers ────────────────────────────────────────────────────
def _macro_fit_score(
    recipe:       dict,
    target_cal:   Optional[float],
    target_prot:  Optional[float],
    target_carbs: Optional[float],
    target_fats:  Optional[float],
) -> tuple:
    """
    Smooth Gaussian scoring — peaks at 1.0 when recipe == target,
    falls off gently. Sigma = 0.5 means ±50% deviation → score ~0.6.

    This is more realistic than a step function because recipe datasets
    contain full-recipe amounts (often 2-3 servings) so perfect per-meal
    alignment is rare.
    """
    import math

    # How important each dimension is
    # Protein weight is higher — most relevant for health-aware recs (Ge et al.)
    DIM_WEIGHTS = {
        "cal":   0.35,
        "prot":  0.40,
        "carbs": 0.15,
        "fats":  0.10,
    }
    SIGMA = 0.60   # tolerance — ±60% deviation gives score ~0.57

    dims = [
        (recipe.get("calories"), target_cal,   "cal"),
        (recipe.get("protein"),  target_prot,  "prot"),
        (recipe.get("carbs"),    target_carbs, "carbs"),
        (recipe.get("fats"),     target_fats,  "fats"),
    ]

    weighted_score = 0.0
    labels = []

    for actual, target, key in dims:
        w = DIM_WEIGHTS[key]
        if not target or target <= 0 or actual is None:
            weighted_score += w * 0.5   # neutral
            continue

        ratio = actual / target
        # Gaussian: score = exp(-(ratio-1)^2 / (2*sigma^2))
        gauss = math.exp(-((ratio - 1.0) ** 2) / (2 * SIGMA ** 2))
        weighted_score += w * gauss

        # Label only when meaningfully off
        if ratio > 1.5:
            labels.append(f"⬆ high {key}")
        elif ratio < 0.5:
            labels.append(f"⬇ low {key}")
        elif 0.85 <= ratio <= 1.15:
            labels.append(f"✅ {key} on target")

    return round(min(1.0, weighted_score), 3), labels


def _budget_fit_score(cost: float, budget: Optional[float]) -> float:
    if not budget or budget <= 0:
        return 0.5
    ratio = cost / budget
    if ratio <= 0.70: return 1.0
    if ratio <= 1.00: return 0.7
    if ratio <= 1.20: return 0.3
    return 0.0


def _build_reason(
    taste_sim:    float,
    macro_score:  float,
    macro_labels: list,
    budget_score: float,
    is_liked:     bool,
    is_disliked:  bool,
    method:       str,
) -> tuple:
    if is_liked:
        primary = "⭐ Based on your favorites"
    elif is_disliked:
        primary = "👎 You disliked similar meals"
    elif method == "cold_start":
        primary = "💪 Best protein value for your budget"
    elif taste_sim >= 0.85:
        primary = "🎯 Strong match with your taste profile"
    elif taste_sim >= 0.70:
        primary = "✨ Similar to meals you enjoy"
    elif macro_score >= 0.85:
        primary = "🥗 Fits your nutritional goals"
    else:
        primary = "🌟 Recommended for you"

    chips = []
    if taste_sim >= 0.70 and method == "personalized":
        chips.append(f"Taste {int(taste_sim * 100)}%")
    if macro_score >= 0.75:
        chips.append(f"Macro fit {int(macro_score * 100)}%")
    if budget_score >= 0.70:
        chips.append("Fits budget")
    chips.extend(macro_labels[:2])

    return primary, chips


# ── History loader ────────────────────────────────────────────────────────────
async def _get_history(user_id: int, db: AsyncSession) -> dict:
    rows = (await db.execute(text("""
        SELECT recipe_id, recipe_name, interaction_type
        FROM recipe_history
        WHERE user_id = :uid
        ORDER BY created_at DESC
        LIMIT 100
    """), {"uid": user_id})).fetchall()

    liked    = [r.recipe_name for r in rows if r.interaction_type in ("liked", "planned")]
    disliked = [r.recipe_name for r in rows if r.interaction_type == "disliked"]
    viewed   = [r.recipe_name for r in rows if r.interaction_type == "viewed"]
    return {"liked": liked, "disliked": disliked, "viewed": viewed, "total": len(rows)}


# ── Main recommendation function ──────────────────────────────────────────────
async def get_recommendations(
    user_id:      int,
    db:           AsyncSession,
    budget_egp:   Optional[float] = None,
    max_calories: Optional[float] = None,
    min_protein:  Optional[float] = None,
    meal_type:    Optional[str]   = None,
    top_k:        int = 10,
    target_cal:   Optional[float] = None,
    target_prot:  Optional[float] = None,
    target_carbs: Optional[float] = None,
    target_fats:  Optional[float] = None,
) -> dict:

    history = await _get_history(user_id, db)
    is_cold = len(history["liked"]) < COLD_START_THRESHOLD

    from app.services.meal_optimizer import _load_priced_recipes
    recipes = await _load_priced_recipes(db)
    if not recipes:
        return {"status": "error", "message": "Upload meals dataset first."}

    method    = "cold_start"
    profile   = None
    name_vecs = None

    if not is_cold:
        try:
            from app.services.nlp_parser import _NLPModel
            model = _NLPModel.get()

            # Encode liked recipes (small — 37 strings, fast)
            liked_vecs = model.encode(history["liked"], convert_to_numpy=True)
            profile    = liked_vecs.mean(axis=0)

            # Encode all recipe names — CACHED globally
            global _RECIPE_VECS_CACHE, _RECIPE_NAMES_CACHE
            current_names = [r["recipe_name"] for r in recipes]
            if _RECIPE_VECS_CACHE is None or _RECIPE_NAMES_CACHE != current_names:
                logger.info(f"Building recipe embeddings cache ({len(current_names)} recipes)...")
                _RECIPE_VECS_CACHE  = model.encode(current_names, convert_to_numpy=True)
                _RECIPE_NAMES_CACHE = current_names
                logger.info("Recipe embeddings cached")
            name_vecs = _RECIPE_VECS_CACHE

            method = "personalized"
        except Exception as e:
            logger.warning(f"MiniLM failed: {e}")

    liked_set    = {n.lower() for n in history["liked"]}
    disliked_set = {n.lower() for n in history["disliked"]}
    viewed_set   = {n.lower() for n in history["viewed"]}

    # ── Score every recipe ────────────────────────────────────────────────────
    for i, r in enumerate(recipes):
        name_lo = r["recipe_name"].lower()

        # Taste similarity
        if method == "personalized" and profile is not None and name_vecs is not None:
            vec  = name_vecs[i]
            norm = np.linalg.norm(profile) * np.linalg.norm(vec)
            taste_sim = float(np.dot(profile, vec) / norm) if norm > 0 else 0.0
        else:
            taste_sim = min(1.0, r.get("protein", 0) / max(r.get("cost", 1), 0.1) / 50.0)

        # Enhancement C: hard exclude disliked, soft penalty for viewed
        if name_lo in disliked_set:
            r["_excluded"] = True
            r["taste_sim"] = 0.0
            r["rec_score"] = -1.0
            continue   # skip scoring entirely
        elif name_lo in viewed_set:
            taste_sim -= 0.05
        taste_sim = max(0.0, min(1.0, taste_sim))

        # Enhancement A: macro + budget fit
        macro_score, macro_labels = _macro_fit_score(r, target_cal, target_prot, target_carbs, target_fats)
        budget_score = _budget_fit_score(r.get("cost", 0), budget_egp)

        r["taste_sim"]    = round(taste_sim, 3)
        r["macro_score"]  = round(macro_score, 3)
        r["macro_labels"] = macro_labels
        r["budget_score"] = round(budget_score, 3)
        r["rec_score"]    = round(W_TASTE * taste_sim + W_MACRO * macro_score + W_BUDGET * budget_score, 3)

    recipes.sort(key=lambda x: x.get("rec_score", 0), reverse=True)

    # ── Health filter + hard exclude disliked ─────────────────────────────────
    filtered = [
        r for r in recipes
        if not r.get("_excluded", False)                                   # hard exclude disliked
        and (not budget_egp   or r.get("cost",     0) <= budget_egp)
        and (not max_calories or r.get("calories", 0) <= max_calories)
        and (not min_protein  or r.get("protein",  0) >= min_protein)
        and (not meal_type    or r.get("meal_type")   == meal_type)
    ] or [r for r in recipes if not r.get("_excluded", False)]

    # Enhancement D: diversity-aware re-ranking
    # Guarantee ≥1 per meal_type, then fill by score with DIVERSITY_CAP
    all_types  = list({r.get("meal_type", "غداء") for r in filtered})
    per_type_min = max(1, top_k // max(len(all_types), 1))

    type_min_taken: dict = {}
    type_cap_taken: dict = {}
    first_pass:  list = []
    second_pass: list = []

    for r in filtered:
        mt = r.get("meal_type", "غداء")
        if type_min_taken.get(mt, 0) < per_type_min:
            type_min_taken[mt] = type_min_taken.get(mt, 0) + 1
            first_pass.append(r)
        else:
            second_pass.append(r)

    for r in second_pass:
        mt = r.get("meal_type", "غداء")
        if type_cap_taken.get(mt, 0) < DIVERSITY_CAP:
            type_cap_taken[mt] = type_cap_taken.get(mt, 0) + 1
            first_pass.append(r)

    first_pass.sort(key=lambda x: x.get("rec_score", 0), reverse=True)
    final = first_pass[:top_k]

    # Enhancement B: explainability
    for r in final:
        primary, chips = _build_reason(
            taste_sim    = r.get("taste_sim", 0),
            macro_score  = r.get("macro_score", 0),
            macro_labels = r.get("macro_labels", []),
            budget_score = r.get("budget_score", 0),
            is_liked     = r["recipe_name"].lower() in liked_set,
            is_disliked  = r["recipe_name"].lower() in disliked_set,
            method       = method,
        )
        r["reason"]       = primary
        r["reason_chips"] = chips

    needs_more = max(0, COLD_START_THRESHOLD - len(history["liked"]))
    return {
        "status":           "ok",
        "method":           method,
        "is_cold_start":    is_cold,
        "liked_count":      len(history["liked"]),
        "history_count":    history["total"],
        "needs_more_likes": needs_more,
        "recommendations":  final,
        "message": (
            "Based on your meal history" if not is_cold
            else f"Like {needs_more} more meal{'s' if needs_more != 1 else ''} to unlock personalized recommendations"
        ),
    }


async def record_interaction(
    user_id: int, recipe_id: int,
    recipe_name: str, interaction_type: str,
    db: AsyncSession,
):
    await db.execute(text("""
        INSERT INTO recipe_history
          (user_id, recipe_id, recipe_name, interaction_type)
        VALUES (:uid, :rid, :rname, :itype)
    """), {"uid": user_id, "rid": recipe_id,
           "rname": recipe_name, "itype": interaction_type})
    await db.commit()