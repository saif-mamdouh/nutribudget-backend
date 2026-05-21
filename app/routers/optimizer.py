"""
routers/optimizer.py
─────────────────────
Two optimization modes:

  POST /optimize/plan          ← ingredient-level (grocery list)
  POST /optimize/plan/from-profile   ← ingredient-level from user profile
  POST /optimize/meal-plan     ← meal-level (real recipes) ← NEW
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth import get_current_user
from app.models.user import User
from app.schemas.optimizer import (
    OptimizeRequest, OptimizeResponse,
    MealPlanRequest, MealPlanResponse,
)
from app.services.optimizer      import optimize_plan
from app.services.meal_optimizer import optimize_meal_plan
from app.models.meal_plan        import MealPlan
from sqlalchemy                  import text
from app.services.optimizer import optimize_plan, compare_plans
router = APIRouter(prefix="/optimize", tags=["Optimizer"])


# ── POST /optimize/plan ───────────────────────────────────────────────────────
@router.post("/plan", response_model=OptimizeResponse)
async def ingredient_plan(
    req: OptimizeRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Ingredient-level MILP.
    Returns raw ingredients (grocery list) that meet macro targets.
    Best for: fitness users who weigh food, keto dieters, bodybuilders.
    """
    return await optimize_plan(req, db)


# ── POST /optimize/plan/from-profile ─────────────────────────────────────────
@router.post("/plan/from-profile", response_model=OptimizeResponse)
async def ingredient_plan_from_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Uses the authenticated user's saved targets."""
    req = OptimizeRequest(
        budget_egp=current_user.daily_budget_egp or 200,
        calories=current_user.daily_calories or 2000,
        protein_g=current_user.daily_protein_g or 60,
        carbs_g=current_user.daily_carbs_g or 0,
        fats_g=current_user.daily_fats_g or 0,
    )
    return await optimize_plan(req, db)


# ── POST /optimize/meal-plan ──────────────────────────────────────────────────
@router.post("/meal-plan")          # removed response_model → allows extra fields in return
async def meal_plan(
    req: MealPlanRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Meal-level MILP — selects real Egyptian recipes from the dataset.
    Weekly plans overwrite the previous weekly plan for this user.
    """
    result = await optimize_meal_plan(req, db, user=user)

    plan_id_saved = None

    if result.status in ("optimal", "feasible"):
        import json as _json
        meals_data = []
        for m in (result.meals or []):
            meals_data.append({
                "recipe_id":   m.recipe_id,
                "recipe_name": m.recipe_name,
                "meal_type":   m.meal_type,
                "day":         m.day,
                "slot":        m.slot,
                "cost_egp":    m.cost_egp,
                "calories":    m.calories,
                "protein_g":   m.protein_g,
                "carbs_g":     m.carbs_g,
                "fats_g":      m.fats_g,
                "prep_time":   m.prep_time,
            })

        plan_name = "Weekly Plan" if req.plan_type == "weekly" else \
                    "Daily Plan"  if req.plan_type == "daily"  else "Single Meal"

        # ── Weekly: overwrite existing plan instead of creating duplicates ──
        if req.plan_type == "weekly":
            try:
                existing = (await db.execute(text("""
                    SELECT id FROM meal_plans
                    WHERE user_id = :uid AND period = 'weekly'
                    ORDER BY created_at DESC LIMIT 1
                """), {"uid": user.id})).fetchone()

                if existing:
                    await db.execute(text("""
                        UPDATE meal_plans
                        SET total_cost_egp  = :cost,
                            total_calories  = :cal,
                            total_protein_g = :prot,
                            total_carbs_g   = :carb,
                            total_fats_g    = :fat,
                            solver_status   = :status,
                            meals_json      = :meals,
                            plan_name       = :name,
                            created_at      = NOW()
                        WHERE id = :pid
                    """), {
                        "cost":   result.total_cost_egp,
                        "cal":    result.total_calories,
                        "prot":   result.total_protein_g,
                        "carb":   result.total_carbs_g,
                        "fat":    result.total_fats_g,
                        "status": result.status,
                        "meals":  _json.dumps(meals_data, ensure_ascii=False),
                        "name":   plan_name,
                        "pid":    existing.id,
                    })
                    await db.commit()
                    plan_id_saved = existing.id
            except Exception as e:
                await db.rollback()
                import logging
                logging.getLogger("nutribudget").warning(f"Weekly overwrite failed: {e}")

        # ── Non-weekly (or overwrite failed): insert new record ──
        if plan_id_saved is None:
            for use_extended in [True, False]:
                try:
                    kwargs = dict(
                        user_id         = user.id,
                        period          = req.plan_type,
                        total_cost_egp  = result.total_cost_egp,
                        total_calories  = result.total_calories,
                        total_protein_g = result.total_protein_g,
                        total_carbs_g   = result.total_carbs_g,
                        total_fats_g    = result.total_fats_g,
                        solver_status   = result.status,
                    )
                    if use_extended:
                        kwargs["meals_json"] = _json.dumps(meals_data, ensure_ascii=False)
                        kwargs["plan_name"]  = plan_name

                    plan_record = MealPlan(**kwargs)
                    db.add(plan_record)
                    await db.commit()
                    await db.refresh(plan_record)
                    plan_id_saved = plan_record.id
                    break
                except Exception as e:
                    await db.rollback()
                    if not use_extended:
                        import logging
                        logging.getLogger("nutribudget").error(f"Plan save failed: {e}")

    # ── Return result as dict so plan_id is always included ──
    result_dict = result.dict() if hasattr(result, 'dict') else result.model_dump()
    result_dict["plan_id"] = plan_id_saved
    return result_dict


# ── GET /optimize/weekly/active ───────────────────────────────────────────────
@router.get("/weekly/active")
async def get_active_weekly_plan(
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """Returns the latest weekly plan with all meals for the calendar view."""
    import json as _json
    from datetime import date, timedelta

    row = (await db.execute(text("""
        SELECT id, total_cost_egp, total_calories, total_protein_g,
               total_carbs_g, total_fats_g, meals_json, created_at, plan_name
        FROM meal_plans
        WHERE user_id = :uid AND period = 'weekly' AND meals_json IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 1
    """), {"uid": user.id})).fetchone()

    if not row or not row.meals_json:
        return {"plan": None}

    meals = _json.loads(row.meals_json)

    # Calculate current day of the plan
    created = row.created_at.date() if row.created_at else date.today()
    today   = date.today()
    day_num = (today - created).days + 1  # Day 1 on creation date
    current_day = day_num if 1 <= day_num <= 7 else None

    return {
        "plan": {
            "plan_id":        row.id,
            "plan_name":      row.plan_name or "Weekly Plan",
            "total_cost_egp": round(float(row.total_cost_egp), 2),
            "total_calories": round(float(row.total_calories), 1),
            "total_protein_g":round(float(row.total_protein_g), 2),
            "created_at":     str(row.created_at),
            "current_day":    current_day,
            "meals":          meals,
        }
    }


# ── GET /optimize/weekly/history ──────────────────────────────────────────────
@router.get("/weekly/history")
async def get_weekly_plan_history(
    db:    AsyncSession = Depends(get_db),
    user:  User         = Depends(get_current_user),
    limit: int          = 10,
):
    """Returns all saved weekly plans (summary list) for the plan switcher."""
    import json as _json
    rows = (await db.execute(text("""
        SELECT id, plan_name, total_cost_egp, total_calories,
               total_protein_g, meals_json, created_at
        FROM meal_plans
        WHERE user_id = :uid AND period = 'weekly' AND meals_json IS NOT NULL
        ORDER BY created_at DESC
        LIMIT :lim
    """), {"uid": user.id, "lim": limit})).fetchall()

    plans = []
    for r in rows:
        try:
            meals = _json.loads(r.meals_json or "[]")
            meal_count = len(meals)
        except Exception:
            meal_count = 0
        plans.append({
            "plan_id":        r.id,
            "plan_name":      r.plan_name or "Weekly Plan",
            "total_cost_egp": round(float(r.total_cost_egp), 2),
            "total_calories": round(float(r.total_calories), 1),
            "total_protein_g":round(float(r.total_protein_g), 2),
            "meal_count":     meal_count,
            "created_at":     str(r.created_at),
        })
    return {"plans": plans}


# ── GET /optimize/weekly/{plan_id} ────────────────────────────────────────────
@router.get("/weekly/{plan_id}")
async def get_weekly_plan_by_id(
    plan_id: int,
    db:      AsyncSession = Depends(get_db),
    user:    User         = Depends(get_current_user),
):
    """Load a specific weekly plan by ID (for plan switcher)."""
    import json as _json
    row = (await db.execute(text("""
        SELECT id, total_cost_egp, total_calories, total_protein_g,
               meals_json, created_at, plan_name
        FROM meal_plans
        WHERE id = :pid AND user_id = :uid AND period = 'weekly'
    """), {"pid": plan_id, "uid": user.id})).fetchone()

    if not row:
        raise HTTPException(404, "Plan not found")

    meals = _json.loads(row.meals_json or "[]")
    return {
        "plan": {
            "plan_id":         row.id,
            "plan_name":       row.plan_name or "Weekly Plan",
            "total_cost_egp":  round(float(row.total_cost_egp), 2),
            "total_calories":  round(float(row.total_calories), 1),
            "total_protein_g": round(float(row.total_protein_g), 2),
            "created_at":      str(row.created_at),
            "meals":           meals,
        }
    }


# ── PATCH /optimize/weekly/{plan_id}/swap ─────────────────────────────────────
class SwapMealRequest(BaseModel):
    day:        int
    meal_type:  str   # فطار / غداء / عشاء
    recipe_id:  int


@router.patch("/weekly/{plan_id}/swap")
async def swap_meal(
    plan_id: int,
    req:     SwapMealRequest,
    db:      AsyncSession = Depends(get_db),
    user:    User         = Depends(get_current_user),
):
    """Swap a single meal in a weekly plan with a new recipe."""
    import json as _json

    # Verify ownership
    plan_row = (await db.execute(text("""
        SELECT id, meals_json, total_cost_egp, total_calories,
               total_protein_g, total_carbs_g, total_fats_g
        FROM meal_plans
        WHERE id = :pid AND user_id = :uid
    """), {"pid": plan_id, "uid": user.id})).fetchone()

    if not plan_row:
        raise HTTPException(404, "Plan not found")

    meals = _json.loads(plan_row.meals_json or "[]")

    # Get new recipe basic info (simple query — no broken JSON aggregation)
    recipe_row = (await db.execute(text("""
        SELECT recipe_id, recipe_name, meal_type, prep_time, ingredients_json
        FROM recipes
        WHERE recipe_id = :rid
        LIMIT 1
    """), {"rid": req.recipe_id})).fetchone()

    if not recipe_row:
        raise HTTPException(404, "Recipe not found")

    # Calculate macros + cost from ingredients directly (no external import)
    import json as _json2
    try:
        ingredients = _json2.loads(recipe_row.ingredients_json or "[]")
    except Exception:
        ingredients = []

    total_cal = total_prot_r = total_carb_r = total_fat_r = total_cost_r = 0.0
    priced_ings = []

    for ing in ingredients:
        ikey = ing.get("name", "")
        wg   = float(ing.get("weight_g", 0))
        if not ikey or wg <= 0:
            continue
        # Look up best price + nutrition for this ingredient
        ing_row = (await db.execute(text("""
            SELECT m.price_per_100g, m.source, p.product_name,
                   n.calories_per_100g, n.protein_g, n.carbs_g, n.fats_g,
                   n.display_name
            FROM ingredient_product_map m
            JOIN nutrition_facts  n ON n.normalized_name = m.ingredient_key
            JOIN fresh_products   p ON p.sku = m.sku
            WHERE m.ingredient_key = :key AND m.price_per_100g > 0
            ORDER BY m.price_per_100g ASC
            LIMIT 1
        """), {"key": ikey})).fetchone()

        if ing_row:
            ic = (float(ing_row.price_per_100g) / 100) * wg
            total_cost_r  += ic
            total_cal     += (float(ing_row.calories_per_100g) / 100) * wg
            total_prot_r  += (float(ing_row.protein_g)         / 100) * wg
            total_carb_r  += (float(ing_row.carbs_g)           / 100) * wg
            total_fat_r   += (float(ing_row.fats_g)            / 100) * wg
            priced_ings.append({
                "name": ikey, "display_name": ing_row.display_name or ikey,
                "product_name": ing_row.product_name or "",
                "source": ing_row.source or "",
                "weight_g": round(wg, 1), "cost_egp": round(ic, 2),
                "calories": round((float(ing_row.calories_per_100g)/100)*wg, 1),
                "protein_g": round((float(ing_row.protein_g)/100)*wg, 2),
                "price_per_100g": float(ing_row.price_per_100g),
            })
        else:
            priced_ings.append({"name": ikey, "display_name": ikey,
                "weight_g": round(wg, 1), "cost_egp": 0, "source": ""})

    new_meal_data = {
        "cost_egp":    round(total_cost_r,  2),
        "calories":    round(total_cal,     1),
        "protein_g":   round(total_prot_r,  2),
        "carbs_g":     round(total_carb_r,  2),
        "fats_g":      round(total_fat_r,   2),
        "ingredients": priced_ings,
    }

    # Build replacement meal
    new_meal = {
        "recipe_id":   req.recipe_id,
        "recipe_name": recipe_row.recipe_name,
        "meal_type":   req.meal_type,
        "day":         req.day,
        "slot":        {"فطار": "breakfast", "غداء": "lunch", "عشاء": "dinner"}.get(req.meal_type, "meal"),
        "cost_egp":    new_meal_data.get("cost_egp", 0),
        "calories":    new_meal_data.get("calories", 0),
        "protein_g":   new_meal_data.get("protein_g", 0),
        "carbs_g":     new_meal_data.get("carbs_g", 0),
        "fats_g":      new_meal_data.get("fats_g", 0),
        "prep_time":   recipe_row.prep_time or 0,
        "ingredients": new_meal_data.get("ingredients", []),
    }

    # Replace the meal in the array
    replaced = False
    for i, meal in enumerate(meals):
        if meal.get("day") == req.day and meal.get("meal_type") == req.meal_type:
            meals[i] = new_meal
            replaced = True
            break

    if not replaced:
        meals.append(new_meal)

    # Recalculate totals
    total_cost = sum(m.get("cost_egp", 0)  for m in meals)
    total_cal  = sum(m.get("calories", 0)  for m in meals)
    total_prot = sum(m.get("protein_g", 0) for m in meals)
    total_carb = sum(m.get("carbs_g", 0)   for m in meals)
    total_fat  = sum(m.get("fats_g", 0)    for m in meals)

    await db.execute(text("""
        UPDATE meal_plans
        SET meals_json      = :meals,
            total_cost_egp  = :cost,
            total_calories  = :cal,
            total_protein_g = :prot,
            total_carbs_g   = :carb,
            total_fats_g    = :fat
        WHERE id = :pid
    """), {
        "meals": _json.dumps(meals, ensure_ascii=False),
        "cost": total_cost, "cal": total_cal,
        "prot": total_prot, "carb": total_carb, "fat": total_fat,
        "pid": plan_id,
    })
    await db.commit()

    return {"status": "swapped", "new_meal": new_meal,
            "new_totals": {"cost": total_cost, "calories": total_cal, "protein": total_prot}}


@router.get("/history")
async def get_plan_history(
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
    limit: int = 20,
):
    """Get user's meal plan history — includes meal names for display."""
    import json as _json
    rows = (await db.execute(text("""
        SELECT id AS plan_id, period, total_cost_egp, total_calories,
               total_protein_g, total_carbs_g, total_fats_g,
               solver_status AS status, created_at, meals_json, plan_name
        FROM meal_plans
        WHERE user_id = :uid
        ORDER BY created_at DESC
        LIMIT :lim
    """), {"uid": user.id, "lim": limit})).fetchall()

    plans = []
    for r in rows:
        # Parse meal names from meals_json
        meal_names = []
        if r.meals_json:
            try:
                meals = _json.loads(r.meals_json)
                meal_names = [m.get("recipe_name", "") for m in meals if m.get("recipe_name")]
            except Exception:
                pass

        plans.append({
            "plan_id":        r.plan_id,
            "period":         r.period,
            "plan_name":      r.plan_name or None,
            "total_cost_egp": round(float(r.total_cost_egp), 2),
            "total_calories": round(float(r.total_calories), 0),
            "total_protein_g":round(float(r.total_protein_g), 1),
            "total_carbs_g":  round(float(r.total_carbs_g), 1),
            "total_fats_g":   round(float(r.total_fats_g), 1),
            "status":         r.status,
            "created_at":     str(r.created_at),
            "meal_names":     meal_names,   # ← used by History page PlanCard
        })

    # Real total count from DB (not capped by limit)
    total_row = (await db.execute(text("""
        SELECT COUNT(*) AS cnt FROM meal_plans WHERE user_id = :uid
    """), {"uid": user.id})).fetchone()
    total_count = total_row.cnt if total_row else len(plans)

    return {"plans": plans, "total": total_count}


# ── DELETE /optimize/history/{plan_id} ───────────────────────────────────────
@router.delete("/history/{plan_id}")
async def delete_plan(
    plan_id: int,
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """Delete a meal plan + its logged meals from daily goals."""
    # Delete linked meal_logs first (so Daily Goals also update on Dashboard)
    await db.execute(text("""
        DELETE FROM meal_logs
        WHERE plan_id = :pid AND user_id = :uid
    """), {"pid": plan_id, "uid": user.id})

    result = await db.execute(text("""
        DELETE FROM meal_plans
        WHERE id = :pid AND user_id = :uid
    """), {"pid": plan_id, "uid": user.id})
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Plan not found or not yours")
    return {"status": "deleted", "plan_id": plan_id}


# ── POST /optimize/add-meal ───────────────────────────────────────────────────
from pydantic import BaseModel as BM

class AddMealRequest(BM):
    recipe_name:  str
    cost_egp:     float = 0.0
    calories:     float = 0.0
    protein_g:    float = 0.0
    carbs_g:      float = 0.0
    fats_g:       float = 0.0
    meal_type:    str   = "غداء"

@router.post("/add-meal")
async def add_meal_to_plan(
    req:  AddMealRequest,
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """Add a single selected meal to history using raw SQL (resilient)."""
    import json as _json
    meals_data = _json.dumps([{
        "recipe_name": req.recipe_name, "meal_type": req.meal_type,
        "cost_egp": req.cost_egp, "calories": req.calories,
        "protein_g": req.protein_g, "carbs_g": req.carbs_g,
        "fats_g": req.fats_g, "day": 1,
    }], ensure_ascii=False)

    # Try with meals_json + plan_name columns (needs migration_weekly_meals.sql)
    for use_extended in [True, False]:
        try:
            if use_extended:
                result = await db.execute(text("""
                    INSERT INTO meal_plans
                      (user_id, period, plan_name, meals_json,
                       total_cost_egp, total_calories, total_protein_g,
                       total_carbs_g, total_fats_g, solver_status)
                    VALUES
                      (:uid, 'single', :pname, :meals,
                       :cost, :cal, :prot, :carb, :fat, 'added')
                """), {"uid": user.id, "pname": req.recipe_name, "meals": meals_data,
                       "cost": req.cost_egp, "cal": req.calories, "prot": req.protein_g,
                       "carb": req.carbs_g, "fat": req.fats_g})
            else:
                result = await db.execute(text("""
                    INSERT INTO meal_plans
                      (user_id, period,
                       total_cost_egp, total_calories, total_protein_g,
                       total_carbs_g, total_fats_g, solver_status)
                    VALUES
                      (:uid, 'single',
                       :cost, :cal, :prot, :carb, :fat, 'added')
                """), {"uid": user.id, "cost": req.cost_egp, "cal": req.calories,
                       "prot": req.protein_g, "carb": req.carbs_g, "fat": req.fats_g})

            await db.commit()
            plan_id = result.lastrowid
            return {"status": "ok", "plan_id": plan_id,
                    "message": f"'{req.recipe_name}' added to your plan history"}
        except Exception as e:
            await db.rollback()
            if not use_extended:
                import logging
                logging.getLogger("nutribudget").error(f"add-meal failed: {e}")
                raise HTTPException(500, f"Failed to save meal: {str(e)}")


# ── POST /optimize/meal-search ────────────────────────────────────────────────
from pydantic import BaseModel

class MealSearchReq(BaseModel):
    query:      str
    budget_egp: Optional[float] = None
    protein_g:  Optional[float] = None
    top_k:      int = 5

@router.post("/meal-search")
async def meal_search(
    req:  MealSearchReq,
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """
    Semantic meal search using MiniLM.
    Respects user forbidden_foods and allergies from profile.
    """
    import json as _json
    from app.services.meal_search import _search_meals, _suggest_protein_alternatives

    results = await _search_meals(req.query, db, top_k=req.top_k * 3, budget_egp=req.budget_egp or 0)

    # ── Filter forbidden foods & allergies ────────────────────────────────────
    forbidden = _json.loads(user.forbidden_foods or "[]") if isinstance(user.forbidden_foods, str) else (user.forbidden_foods or [])
    allergies = _json.loads(user.allergies       or "[]") if isinstance(user.allergies,       str) else (user.allergies       or [])
    blocked   = {f.lower().strip() for f in forbidden + allergies if f}

    if blocked:
        filtered = []
        for r in results:
            recipe_name = r.get("recipe_name", "").lower()
            # Check recipe name
            if any(b in recipe_name for b in blocked):
                continue
            # Check ingredients
            ing_names = " ".join(
                str(i.get("name", "")) + " " + str(i.get("display_name", ""))
                for i in r.get("ingredients", [])
            ).lower()
            if any(b in ing_names for b in blocked):
                continue
            filtered.append(r)
        results = filtered[:req.top_k]
    else:
        results = results[:req.top_k]

    # For each result that fails protein filter, add protein suggestions
    protein_suggestions = []
    if req.protein_g and results:
        best_meal = results[0]
        if best_meal.get("protein_g", 0) < req.protein_g:
            gap = req.protein_g - best_meal.get("protein_g", 0)
            protein_suggestions = await _suggest_protein_alternatives(
                current_protein=best_meal.get("protein_g", 0),
                target_protein=req.protein_g,
                budget=req.budget_egp or 500,
                db=db,
                top_k=3,
            )

    return {
        "status":               "ok",
        "query":                req.query,
        "budget_filter":        req.budget_egp,
        "protein_filter":       req.protein_g,
        "results":              results,
        "protein_suggestions":  protein_suggestions,
        "protein_gap_g":        round(req.protein_g - results[0].get("protein_g", 0), 1) if req.protein_g and results else 0,
    }


# ── POST /optimize/log-meal ───────────────────────────────────────────────────
class LogMealRequest(BaseModel):
    plan_id:     Optional[int] = None   # optional — weekly logs may not need plan_id
    recipe_id:   Optional[int] = None
    recipe_name: str
    meal_type:   str
    day_num:     int = 0
    calories:    float = 0
    protein_g:   float = 0
    carbs_g:     float = 0
    fats_g:      float = 0
    cost_egp:    float = 0


@router.post("/log-meal")
async def log_meal(
    req:  LogMealRequest,
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """Mark a meal as eaten. Prevents duplicates — same meal+type+day logged twice returns existing ID."""
    # Check if already logged today (prevents double-logging same meal)
    existing = (await db.execute(text("""
        SELECT id FROM meal_logs
        WHERE user_id    = :uid
          AND recipe_name = :name
          AND meal_type   = :mtype
          AND day_num     = :day
          AND DATE(logged_at) = CURDATE()
        LIMIT 1
    """), {"uid": user.id, "name": req.recipe_name,
           "mtype": req.meal_type, "day": req.day_num})).fetchone()

    if existing:
        return {"status": "already_logged", "id": existing.id,
                "recipe_name": req.recipe_name}

    result = await db.execute(text("""
        INSERT INTO meal_logs
          (user_id, plan_id, recipe_id, recipe_name, meal_type,
           day_num, calories, protein_g, carbs_g, fats_g, cost_egp)
        VALUES
          (:uid, :plan_id, :recipe_id, :name, :mtype,
           :day, :cal, :prot, :carb, :fat, :cost)
    """), {
        "uid": user.id, "plan_id": req.plan_id,
        "recipe_id": req.recipe_id, "name": req.recipe_name,
        "mtype": req.meal_type, "day": req.day_num,
        "cal": req.calories, "prot": req.protein_g,
        "carb": req.carbs_g, "fat": req.fats_g, "cost": req.cost_egp,
    })
    await db.commit()
    return {"status": "logged", "id": result.lastrowid, "recipe_name": req.recipe_name}


@router.delete("/log-meal/{log_id}")
async def unlog_meal_by_id(
    log_id: int,
    db:     AsyncSession = Depends(get_db),
    user:   User         = Depends(get_current_user),
):
    """Unmark a meal by its log row ID (preferred method)."""
    await db.execute(text("""
        DELETE FROM meal_logs WHERE id = :id AND user_id = :uid
    """), {"id": log_id, "uid": user.id})
    await db.commit()
    return {"status": "unlogged", "id": log_id}


# ── DELETE /optimize/log-meal (body-based, legacy) ────────────────────────────
class UnlogMealRequest(BaseModel):
    plan_id:   Optional[int] = None
    recipe_id: Optional[int] = None
    day_num:   int = 0


@router.delete("/log-meal")
async def unlog_meal(
    req:  UnlogMealRequest,
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """Unmark a meal (remove from today's log) by plan+recipe+day."""
    await db.execute(text("""
        DELETE FROM meal_logs
        WHERE user_id  = :uid
          AND plan_id  = :plan_id
          AND recipe_id= :recipe_id
          AND day_num  = :day
          AND DATE(logged_at) = CURDATE()
        LIMIT 1
    """), {"uid": user.id, "plan_id": req.plan_id,
           "recipe_id": req.recipe_id, "day": req.day_num})
    await db.commit()
    return {"status": "unlogged"}


# ── GET /optimize/today-logs ──────────────────────────────────────────────────
@router.get("/today-logs")
async def get_today_logs(
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """Returns all meals logged today (includes row id for unlogging)."""
    rows = (await db.execute(text("""
        SELECT id, recipe_id, recipe_name, meal_type, plan_id, day_num,
               calories, protein_g, carbs_g, fats_g, cost_egp, logged_at
        FROM meal_logs
        WHERE user_id = :uid AND DATE(logged_at) = CURDATE()
        ORDER BY logged_at ASC
    """), {"uid": user.id})).fetchall()

    meals = [dict(r._mapping) for r in rows]
    return {
        "meals":  meals,
        "totals": {
            "calories":  round(sum(m["calories"]  for m in meals), 1),
            "protein_g": round(sum(m["protein_g"] for m in meals), 2),
            "carbs_g":   round(sum(m["carbs_g"]   for m in meals), 2),
            "fats_g":    round(sum(m["fats_g"]     for m in meals), 2),
            "cost_egp":  round(sum(m["cost_egp"]  for m in meals), 2),
        }
    }


# ── GET /optimize/weekly-calories ─────────────────────────────────────────────
@router.get("/weekly-calories")
async def get_weekly_calories(
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """
    Returns daily calorie totals for the last 7 days.
    Source priority: meal_logs (actual) → meal_plans (fallback).
    Used by the Dashboard weekly chart.
    """
    from datetime import date, timedelta

    # ── Primary: meal_logs (explicitly logged meals) ──────────────────────────
    log_rows = (await db.execute(text("""
        SELECT
            DATE(logged_at)        AS day,
            SUM(calories)          AS calories,
            SUM(protein_g)         AS protein_g,
            SUM(carbs_g)           AS carbs_g,
            SUM(fats_g)            AS fats_g,
            SUM(cost_egp)          AS cost_egp,
            COUNT(*)               AS meal_count
        FROM meal_logs
        WHERE user_id   = :uid
          AND logged_at >= CURDATE() - INTERVAL 6 DAY
        GROUP BY DATE(logged_at)
        ORDER BY day ASC
    """), {"uid": user.id})).fetchall()

    # ── Fallback: meal_plans (any plan created that day) ─────────────────────
    plan_rows = (await db.execute(text("""
        SELECT
            DATE(created_at)                          AS day,
            SUM(total_calories / CASE WHEN period='weekly' THEN 7 ELSE 1 END)   AS calories,
            SUM(total_protein_g / CASE WHEN period='weekly' THEN 7 ELSE 1 END)  AS protein_g,
            SUM(total_carbs_g / CASE WHEN period='weekly' THEN 7 ELSE 1 END)    AS carbs_g,
            SUM(total_fats_g / CASE WHEN period='weekly' THEN 7 ELSE 1 END)     AS fats_g,
            SUM(total_cost_egp / CASE WHEN period='weekly' THEN 7 ELSE 1 END)   AS cost_egp,
            COUNT(*)                                  AS meal_count
        FROM meal_plans
        WHERE user_id    = :uid
          AND created_at >= CURDATE() - INTERVAL 6 DAY
        GROUP BY DATE(created_at)
        ORDER BY day ASC
    """), {"uid": user.id})).fetchall()

    # Merge: prefer log_rows, fill missing days from plan_rows
    today     = date.today()
    log_map   = {str(r.day): r for r in log_rows}
    plan_map  = {str(r.day): r for r in plan_rows}

    days = []
    for i in range(6, -1, -1):
        d     = today - timedelta(days=i)
        d_str = str(d)
        r     = log_map.get(d_str) or plan_map.get(d_str)   # logs first
        days.append({
            "date":       d_str,
            "calories":   round(float(r.calories  or 0), 1) if r else 0.0,
            "protein_g":  round(float(r.protein_g or 0), 2) if r else 0.0,
            "carbs_g":    round(float(r.carbs_g   or 0), 2) if r else 0.0,
            "fats_g":     round(float(r.fats_g    or 0), 2) if r else 0.0,
            "cost_egp":   round(float(r.cost_egp  or 0), 2) if r else 0.0,
            "meal_count": int(r.meal_count or 0)             if r else 0,
        })

    return {"days": days}


# ── POST /optimize/smart-summary ─────────────────────────────────────────────
class SmartSummaryRequest(BaseModel):
    plan_type:      str
    total_cost_egp: float
    total_calories: float
    total_protein_g:float
    total_carbs_g:  float
    total_fats_g:   float
    total_meals:    int
    budget_egp:     float
    calories_target:float
    protein_target: float
    meal_names:     list[str] = []
    user_goal:      Optional[str] = None   # "muscle" | "cut" | "budget" | None

@router.post("/smart-summary")
async def smart_summary(
    req: SmartSummaryRequest,
    user: User = Depends(get_current_user),
):
    """Generate a Groq-powered Arabic summary of the meal plan."""
    try:
        from groq import Groq
        from app.core.config import settings
        client = Groq(api_key=settings.GROQ_API_KEY)

        meals_str = "، ".join(req.meal_names[:8]) if req.meal_names else "متنوعة"
        goal_map  = {"muscle": "بناء عضل", "cut": "حرق دهون", "budget": "توفير", None: "صحة عامة"}
        goal_ar   = goal_map.get(req.user_goal, "صحة عامة")
        saved_pct = round((1 - req.total_cost_egp / req.budget_egp) * 100) if req.budget_egp > 0 else 0
        prot_ok   = req.total_protein_g >= req.protein_target * 0.95
        cal_ok    = req.total_calories  >= req.calories_target * 0.95
        period    = "أسبوعية" if req.plan_type == "weekly" else ("يومية" if req.plan_type == "daily" else "فردية")

        prompt = f"""أنت خبير تغذية مصري. اكتب ملخصاً مفيداً لخطة وجبات في جملتين أو ثلاثة بالعربية الفصيحة البسيطة.

بيانات الخطة ({period}):
- الهدف: {goal_ar}
- التكلفة: {req.total_cost_egp:.0f} EGP (وفّر {saved_pct}% من الـ budget)
- السعرات: {req.total_calories:.0f} kcal ({f"✅ محقق" if cal_ok else f"❌ أقل من الهدف {req.calories_target:.0f}"})
- البروتين: {req.total_protein_g:.0f}g ({f"✅ محقق" if prot_ok else f"❌ أقل من الهدف {req.protein_target:.0f}g"})
- الوجبات: {meals_str}

اكتب الملخص مباشرة بدون مقدمة. ركّز على: هل الخطة مناسبة للهدف؟ أبرز إيجابية وتوصية واحدة."""

        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=180,
        )
        return {"summary": resp.choices[0].message.content.strip()}

    except Exception as e:
        # Fallback: template-based summary
        saved_pct = round((1 - req.total_cost_egp / req.budget_egp) * 100) if req.budget_egp > 0 else 0
        goal_map  = {"muscle": "بناء العضل", "cut": "حرق الدهون", "budget": "التوفير", None: "الصحة"}
        goal_ar   = goal_map.get(req.user_goal, "الصحة")
        summary   = f"الخطة {('محققة ✅' if req.total_protein_g >= req.protein_target * 0.95 else 'تحتاج تعديل')} لهدف {goal_ar} — "
        summary  += f"بروتين {req.total_protein_g:.0f}g · {req.total_calories:.0f} kcal · "
        summary  += f"وفّرت {saved_pct}% من الـ budget."
        return {"summary": summary}

@router.post("/compare")
async def compare_milp_vs_greedy(
    req:  OptimizeRequest,
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    return await compare_plans(req, db)