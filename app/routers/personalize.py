"""
routers/personalize.py
────────────────────────
GET  /personalize/recommendations   ← get personalized meal recs
POST /personalize/interact          ← record like/dislike/viewed
GET  /personalize/history           ← user's interaction history
"""

from fastapi import APIRouter, Depends
from typing import Optional, Literal
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth import get_current_user
from app.models.user import User
from app.services.personalization import get_recommendations, record_interaction

router = APIRouter(prefix="/personalize", tags=["Personalization"])


class InteractionRequest(BaseModel):
    recipe_id:        int
    recipe_name:      str
    interaction_type: Literal["viewed", "liked", "disliked", "planned"]


@router.get("/recommendations")
async def recommendations(
    budget_egp:   Optional[float] = None,
    max_calories: Optional[float] = None,
    min_protein:  Optional[float] = None,
    meal_type:    Optional[str]   = None,
    top_k:        int             = 10,
    db:           AsyncSession    = Depends(get_db),
    user:         User            = Depends(get_current_user),
):
    """
    History-based recipe recommendations using MiniLM embeddings.
    Implements Ge et al. (2015) — Health-aware Food Recommendation.
    Passes user's saved macro targets for accurate nutritional fit scoring.
    """
    # Use user's saved daily targets as macro targets for scoring
    # This fixes the "50% nutritional fit for everyone" bug
    target_cal   = float(user.daily_calories  or 0) or None
    target_prot  = float(user.daily_protein_g or 0) or None
    target_carbs = float(user.daily_carbs_g   or 0) or None
    target_fats  = float(user.daily_fats_g    or 0) or None
    effective_budget = budget_egp or (float(user.daily_budget_egp or 0) or None)

    return await get_recommendations(
        user_id=user.id, db=db,
        budget_egp=effective_budget,
        max_calories=max_calories,
        min_protein=min_protein,
        meal_type=meal_type,
        top_k=top_k,
        target_cal=target_cal,
        target_prot=target_prot,
        target_carbs=target_carbs,
        target_fats=target_fats,
    )


@router.post("/interact")
async def interact(
    req:  InteractionRequest,
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """Record user interaction with a recipe (like/dislike/viewed/planned)."""
    await record_interaction(
        user_id=user.id, recipe_id=req.recipe_id,
        recipe_name=req.recipe_name, interaction_type=req.interaction_type,
        db=db,
    )
    return {"status": "ok", "recorded": req.interaction_type}


@router.get("/history")
async def history(
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """Get user's recipe interaction history with recipe details."""
    from sqlalchemy import text
    rows = (await db.execute(text("""
        SELECT
            rh.recipe_name,
            rh.recipe_id,
            rh.interaction_type,
            rh.created_at,
            r.meal_type,
            r.prep_time
        FROM recipe_history rh
        LEFT JOIN recipes r ON r.recipe_id = rh.recipe_id
        WHERE rh.user_id = :uid
        ORDER BY rh.created_at DESC
        LIMIT 100
    """), {"uid": user.id})).fetchall()
    return {
        "history": [
            {
                "recipe_name": r.recipe_name,
                "recipe_id":   r.recipe_id,
                "type":        r.interaction_type,
                "date":        str(r.created_at),
                "meal_type":   r.meal_type or "",
                "prep_time":   r.prep_time or 0,
            }
            for r in rows
        ]
    }


@router.get("/liked-recipes")
async def get_liked_recipes(
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """
    Returns all recipes the user has liked, with full cost + macros
    computed from the same pipeline as /recommendations.
    """
    from sqlalchemy import text
    from app.services.meal_optimizer import _load_priced_recipes

    # 1. Get liked recipe IDs/names from history
    rows = (await db.execute(text("""
        SELECT DISTINCT
            rh.recipe_id,
            rh.recipe_name,
            MAX(rh.created_at) AS liked_at
        FROM recipe_history rh
        WHERE rh.user_id = :uid
          AND rh.interaction_type = 'liked'
        GROUP BY rh.recipe_id, rh.recipe_name
        ORDER BY liked_at DESC
    """), {"uid": user.id})).fetchall()

    if not rows:
        return {"recipes": [], "count": 0}

    liked_ids   = {r.recipe_id for r in rows if r.recipe_id}
    liked_names = {r.recipe_name for r in rows}

    # 2. Get full recipe details (cost + macros) from the priced pipeline
    all_priced = await _load_priced_recipes(db)

    # Match by recipe_id first, fallback to recipe_name
    matched = []
    for r in all_priced:
        if r.get("recipe_id") in liked_ids or r.get("recipe_name") in liked_names:
            matched.append(r)

    # 3. Format response — same shape as /recommendations
    recipes = [
        {
            "recipe_id":    r.get("recipe_id"),
            "recipe_name":  r.get("recipe_name"),
            "meal_type":    r.get("meal_type", ""),
            "prep_time":    r.get("prep_time", 0),
            "calories":     float(r.get("calories", 0) or 0),
            "protein":      float(r.get("protein",  0) or 0),
            "carbs":        float(r.get("carbs",    0) or 0),
            "fats":         float(r.get("fats",     0) or 0),
            "cost":         float(r.get("cost",     0) or 0),
            "is_liked":     True,
            "ingredients":  r.get("ingredients", []),
            "reason_chips": ["Liked"],
            "reason":       "❤️ Liked",
        }
        for r in matched
    ]

    return {"recipes": recipes, "count": len(recipes)}




@router.delete("/history/{recipe_id}")
async def unlike_meal(
    recipe_id: int,
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """Remove a liked interaction (un-like a meal)."""
    from sqlalchemy import text
    await db.execute(text("""
        DELETE FROM recipe_history
        WHERE user_id = :uid
          AND recipe_id = :rid
          AND interaction_type = 'liked'
    """), {"uid": user.id, "rid": recipe_id})
    await db.commit()
    return {"status": "ok", "unliked_recipe_id": recipe_id}