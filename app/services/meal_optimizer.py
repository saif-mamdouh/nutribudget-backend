"""
services/meal_optimizer.py  (v4)
──────────────────────────────────
Fix v4: _assign_slots now INTERLEAVES meal types per day:
  Day 1 = فطار[0] + غداء[0] + عشاء[0]
  Day 2 = فطار[1] + غداء[1] + عشاء[1]
  ...
Previously it sorted ALL فطار → ALL غداء → ALL عشاء then did idx//3,
so Day 1 got 3× فطار and 0 غداء/عشاء → frontend showed "—".
"""

import json
import logging
import random
import time
from collections import defaultdict
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.optimizer import MealPlanRequest, MealPlanResponse, PlannedMeal

logger = logging.getLogger("nutribudget.meal_optimizer")

PLAN_SLOTS = {
    "single":  {"فطار": 0, "غداء": 0, "عشاء": 0, "any": 1},
    "daily":   {"فطار": 1, "غداء": 1, "عشاء": 1, "any": 0},
    "weekly":  {"فطار": 7, "غداء": 7, "عشاء": 7, "any": 0},
}
SLOT_EN = {"فطار": "breakfast", "غداء": "lunch", "عشاء": "dinner"}
SERVING_LIMIT = {"فطار": 400, "غداء": 600, "عشاء": 500}

CATEGORY_FILTER: dict = {
    "chicken":          ["Meat & Poultry", "Fresh Food"],
    "chicken_breast":   ["Meat & Poultry", "Fresh Food"],
    "chicken_thigh":    ["Meat & Poultry", "Fresh Food"],
    "whole_chicken":    ["Meat & Poultry", "Fresh Food"],
    "grilled_chicken":  ["Meat & Poultry", "Fresh Food"],
    "ground_beef":      ["Meat & Poultry", "Fresh Food"],
    "beef":             ["Meat & Poultry", "Fresh Food"],
    "beef_steak":       ["Meat & Poultry", "Fresh Food"],
    "lamb":             ["Meat & Poultry", "Fresh Food"],
    "lamb_whole":       ["Meat & Poultry", "Fresh Food"],
    "liver":            ["Meat & Poultry", "Fresh Food"],
    "chicken_liver":    ["Meat & Poultry", "Fresh Food"],
    "sausage":          ["Meat & Poultry"],
    "fish":             ["Fish & Seafood"],
    "fish_fillet":      ["Fish & Seafood"],
    "shrimp":           ["Fish & Seafood"],
    "tuna_canned":      ["Canned & Preserved"],
    "rice":             ["Grains & Legumes"],
    "pasta":            ["Grains & Legumes"],
    "spaghetti":        ["Grains & Legumes"],
    "macaroni":         ["Grains & Legumes"],
    "lentils":          ["Grains & Legumes"],
    "red_lentils":      ["Grains & Legumes"],
    "chickpeas":        ["Grains & Legumes"],
    "fava_beans":       ["Grains & Legumes"],
    "fava_beans_dried": ["Grains & Legumes"],
    "oats":             ["Grains & Legumes"],
    "bulgur":           ["Grains & Legumes"],
    "flour":            ["Grains & Legumes"],
    "semolina":         ["Grains & Legumes"],
    "milk":             ["Dairy"],
    "egg":              ["Dairy"],
    "eggs":             ["Dairy"],
    "butter":           ["Dairy"],
    "ghee":             ["Dairy", "Oils & Condiments"],
    "yogurt":           ["Dairy"],
    "yoghurt":          ["Dairy"],
    "white_cheese":     ["Dairy"],
    "feta_cheese":      ["Dairy"],
    "mozzarella":       ["Dairy"],
    "cheddar":          ["Dairy"],
    "cream":            ["Dairy"],
    "tomato":           ["Vegetables & Fruits", "Fresh Food"],
    "potato":           ["Vegetables & Fruits", "Fresh Food"],
    "onion":            ["Vegetables & Fruits", "Fresh Food"],
    "garlic":           ["Vegetables & Fruits", "Fresh Food"],
    "carrot":           ["Vegetables & Fruits", "Fresh Food"],
    "eggplant":         ["Vegetables & Fruits", "Fresh Food"],
    "zucchini":         ["Vegetables & Fruits", "Fresh Food"],
    "spinach":          ["Vegetables & Fruits", "Fresh Food"],
    "molokhia":         ["Vegetables & Fruits", "Fresh Food"],
    "oil":              ["Oils & Condiments"],
    "olive_oil":        ["Oils & Condiments"],
    "tomato_paste":     ["Oils & Condiments", "Canned & Preserved"],
    "tomato_sauce":     ["Oils & Condiments", "Canned & Preserved"],
    "tahini":           ["Oils & Condiments"],
    "honey":            ["Oils & Condiments"],
    "bread":            ["Bakery & Bread"],
    "toast_bread":      ["Bakery & Bread"],
    "nuts":             ["Nuts & Dried Fruits"],
    "cashews":          ["Nuts & Dried Fruits"],
    "raisins":          ["Nuts & Dried Fruits"],
    "dates":            ["Nuts & Dried Fruits"],
}


def _estimate_servings(total_g: float, meal_type: str) -> int:
    limit = SERVING_LIMIT.get(meal_type, 500)
    return max(1, round(total_g / limit))


# ── Recipe cache ─────────────────────────────────────────────────────────────
# Caches the result of _load_priced_recipes(). Invalidated on product/map updates.
# Key: source_filter string ('' for None). Value: list of priced recipe dicts.
_PRICED_RECIPES_CACHE: dict = {}

def invalidate_priced_recipes_cache():
    """Call this whenever a product or ingredient mapping is updated."""
    global _PRICED_RECIPES_CACHE
    _PRICED_RECIPES_CACHE = {}


async def _load_priced_recipes(db: AsyncSession, source_filter: Optional[str] = None) -> list:
    # Check cache first
    cache_key = source_filter or ""
    if cache_key in _PRICED_RECIPES_CACHE:
        return _PRICED_RECIPES_CACHE[cache_key]

    # Import smart resolver (fine-tuned Egyptian food model)
    try:
        from app.services.smart_ingredient_resolver import resolver
        if not resolver._initialized:
            resolver.initialize()
        use_smart = resolver.is_fine_tuned
    except Exception:
        resolver   = None
        use_smart  = False

    map_sql = text("""
        SELECT m.ingredient_key, m.price_per_100g, m.source, p.category,
               p.product_name,
               n.display_name, n.calories_per_100g, n.protein_g, n.carbs_g, n.fats_g
        FROM ingredient_product_map m
        JOIN nutrition_facts  n ON n.normalized_name = m.ingredient_key
        JOIN fresh_products   p ON p.sku             = m.sku
        WHERE m.price_per_100g > 0 AND (:source IS NULL OR m.source = :source)
        ORDER BY m.ingredient_key, m.price_per_100g ASC
    """)
    map_rows = (await db.execute(map_sql, {"source": source_filter})).fetchall()

    raw_by_key: dict = defaultdict(list)
    for r in map_rows:
        raw_by_key[r.ingredient_key].append(r)

    price_map: dict = {}
    for key, candidates in raw_by_key.items():
        allowed_cats = CATEGORY_FILTER.get(key)
        filtered = [r for r in candidates if r.category in allowed_cats] if allowed_cats else candidates
        if not filtered:
            filtered = candidates

        # ── Smart matching (fine-tuned model) ────────────────────────────────
        if use_smart and len(filtered) > 1:
            try:
                product_names = [r.product_name for r in filtered]
                best_idx      = resolver.best_match_idx(key, filtered, product_names)
                best          = filtered[best_idx]
            except Exception:
                best = min(filtered, key=lambda r: float(r.price_per_100g))
        else:
            # Fallback: cheapest product (original behavior)
            best = min(filtered, key=lambda r: float(r.price_per_100g))

        price_map[key] = {
            "price_per_100g": float(best.price_per_100g),
            "display_name":   best.display_name or key.replace("_", " ").title(),
            "product_name":   best.product_name or "",
            "source":         best.source or "",
            "calories": float(best.calories_per_100g), "protein": float(best.protein_g),
            "carbs":    float(best.carbs_g),           "fats":    float(best.fats_g),
        }

    recipe_rows = (await db.execute(text(
        "SELECT recipe_id, recipe_name, meal_type, ingredients_json, prep_time FROM recipes"
    ))).fetchall()

    recipes, skipped = [], 0
    for r in recipe_rows:
        try:
            ingredients = json.loads(r.ingredients_json)
        except Exception:
            skipped += 1; continue

        total_w = cost = cal = prot = carbs = fats = 0.0
        missing = 0
        ing_list = []

        for ing in ingredients:
            key = ing.get("name", "")
            wg  = float(ing.get("weight_g", 0))
            total_w += wg
            if key in price_map and wg > 0:
                p = price_map[key]
                ic = (p["price_per_100g"] / 100) * wg
                cost += ic; cal += (p["calories"] / 100) * wg
                prot += (p["protein"] / 100) * wg; carbs += (p["carbs"] / 100) * wg
                fats += (p["fats"]    / 100) * wg
                ing_list.append({"name": key, "display_name": p["display_name"],
                    "product_name": p.get("product_name",""), "source": p.get("source",""),
                    "price_per_100g": p["price_per_100g"], "weight_g": wg,
                    "cost_egp": round(ic,2), "calories": round((p["calories"]/100)*wg,1),
                    "protein_g": round((p["protein"]/100)*wg,2)})
            else:
                missing += 1
                ing_list.append({"name": key, "display_name": key.replace("_"," ").title(),
                    "weight_g": wg, "cost_egp": 0, "calories": 0, "protein_g": 0})

        if missing / max(len(ingredients), 1) > 0.4 or cost <= 0 or cal <= 0:
            skipped += 1; continue

        meal_type = r.meal_type or "غداء"
        servings  = _estimate_servings(total_w, meal_type)
        div       = float(servings)
        ing_ps    = [{**i, "weight_g": round(i["weight_g"]/div,1),
            "cost_egp": round(i["cost_egp"]/div,2), "calories": round(i["calories"]/div,1),
            "protein_g": round(i["protein_g"]/div,2)} for i in ing_list]

        recipes.append({"recipe_id": r.recipe_id, "recipe_name": r.recipe_name,
            "meal_type": meal_type, "ingredients": ing_ps, "prep_time": r.prep_time or 0,
            "servings": servings, "cost": round(cost/div,2), "calories": round(cal/div,1),
            "protein": round(prot/div,2), "carbs": round(carbs/div,2), "fats": round(fats/div,2)})

    logger.info(f"📖 {len(recipes)} recipes loaded ({skipped} skipped)")
    # Store in cache before returning
    _PRICED_RECIPES_CACHE[cache_key] = recipes
    return recipes


def _solve(recipes: list, req: MealPlanRequest) -> dict:
    import pulp
    t0    = time.perf_counter()
    slots = PLAN_SLOTS[req.plan_type]
    total = sum(slots.values())

    if not recipes:
        return {"status": "infeasible", "reason": "No recipes in DB"}

    cands = ([r for r in recipes if r["meal_type"] == req.meal_type] or recipes
             if req.plan_type == "single" and req.meal_type else recipes)

    n = len(cands)
    has_budget = bool(req.budget_egp and req.budget_egp < 9999)
    diversity_bonus = [random.uniform(0.60, 1.40) for _ in range(n)]

    def solve_lp(protein_factor=1.0, protein_max=1.20, budget_factor=1.0,
                 slot_slack=0, cal_window=0.15):
        prob = pulp.LpProblem("NutriBudget", pulp.LpMinimize)
        x = [pulp.LpVariable(f"x{i}", lowBound=0, upBound=req.max_repeat,
                             cat="Integer") for i in range(n)]
        prob += pulp.lpSum(cands[i]["cost"] / max(diversity_bonus[i], 0.1) * x[i] for i in range(n))
        prob += pulp.lpSum(cands[i]["calories"] * x[i] for i in range(n)) >= req.calories*(1-cal_window), "CalMin"
        prob += pulp.lpSum(cands[i]["calories"] * x[i] for i in range(n)) <= req.calories*(1+cal_window), "CalMax"
        prob += pulp.lpSum(cands[i]["protein"]  * x[i] for i in range(n)) >= req.protein_g*protein_factor, "ProtMin"
        prob += pulp.lpSum(cands[i]["protein"]  * x[i] for i in range(n)) <= req.protein_g*protein_max, "ProtMax"
        if has_budget:
            prob += pulp.lpSum(cands[i]["cost"] * x[i] for i in range(n)) <= req.budget_egp*budget_factor, "Budget"
        prob += pulp.lpSum(x[i] for i in range(n)) == total, "Total"
        if req.plan_type != "single":
            for mtype, count in slots.items():
                if mtype == "any" or count == 0: continue
                idx = [i for i in range(n) if cands[i]["meal_type"] == mtype]
                if not idx: continue
                prob += pulp.lpSum(x[i] for i in idx) >= max(0, count-slot_slack), f"SlotMin_{mtype}"
                prob += pulp.lpSum(x[i] for i in idx) <= count+slot_slack,         f"SlotMax_{mtype}"
        prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=25))
        return pulp.LpStatus[prob.status], x

    status, x = "infeasible", None
    for att in [
        dict(protein_factor=1.00, protein_max=1.15, budget_factor=1.0, slot_slack=0, cal_window=0.10),
        dict(protein_factor=0.95, protein_max=1.25, budget_factor=1.0, slot_slack=1, cal_window=0.15),
        dict(protein_factor=0.85, protein_max=1.40, budget_factor=1.1, slot_slack=2, cal_window=0.25),
        dict(protein_factor=0.75, protein_max=1.60, budget_factor=1.2, slot_slack=3, cal_window=0.40),
    ]:
        status, x = solve_lp(**att)
        if status in ("Optimal", "Feasible"): break

    ms = round((time.perf_counter() - t0) * 1000, 1)
    if status not in ("Optimal", "Feasible") or x is None:
        return {"status": "infeasible", "solve_time_ms": ms,
                "reason": "No valid plan found. Try increasing budget or reducing protein target."}

    selected = []
    for i in range(n):
        for _ in range(int(round(pulp.value(x[i]) or 0))):
            selected.append(cands[i].copy())

    tc=sum(m["cost"] for m in selected); tl=sum(m["calories"] for m in selected)
    tp=sum(m["protein"] for m in selected); th=sum(m["carbs"] for m in selected)
    tf=sum(m["fats"] for m in selected)
    return {"status": "optimal" if status=="Optimal" else "feasible",
            "solve_time_ms": ms, "selected": selected,
            "total_cost": round(tc,2), "total_calories": round(tl,1),
            "total_protein": round(tp,2), "total_carbs": round(th,2), "total_fats": round(tf,2),
            "budget_used_pct": round(tc/req.budget_egp*100,1) if req.budget_egp else 0,
            "calories_met": tl>=req.calories*0.97, "protein_met": tp>=req.protein_g*0.97,
            "solver_message": f"CBC: {status} in {ms}ms · {len(selected)} meals planned."}


def _assign_slots(selected: list, plan_type: str) -> tuple:
    """
    v4 FIX: Interleave per day → Day1=[فطار[0], غداء[0], عشاء[0]]
    OLD bug: sort all by type → sequential idx//3
      → Day1=[فطار,فطار,فطار], Day2=[فطار,غداء,غداء] ...
    """
    if plan_type == "single":
        m = selected[0]
        return [PlannedMeal(recipe_id=m["recipe_id"], recipe_name=m["recipe_name"],
            meal_type=m["meal_type"], day=None, slot=None, ingredients=m["ingredients"],
            cost_egp=m["cost"], calories=m["calories"], protein_g=m["protein"],
            carbs_g=m["carbs"], fats_g=m["fats"], prep_time=m["prep_time"])], {}

    if plan_type == "daily":
        return [PlannedMeal(recipe_id=m["recipe_id"], recipe_name=m["recipe_name"],
            meal_type=m["meal_type"], day=1, slot=SLOT_EN.get(m["meal_type"],"meal"),
            ingredients=m["ingredients"], cost_egp=m["cost"], calories=m["calories"],
            protein_g=m["protein"], carbs_g=m["carbs"], fats_g=m["fats"],
            prep_time=m["prep_time"]) for m in selected], {}

    # ── Weekly: group by type then interleave ─────────────────────────────────
    by_type: dict = {"فطار": [], "غداء": [], "عشاء": []}
    for m in selected:
        by_type.get(m["meal_type"], by_type["غداء"]).append(m)

    planned: list = []
    days_dict: dict = defaultdict(list)
    num_days = max(len(v) for v in by_type.values())

    for day in range(1, num_days + 1):
        for mtype in ["فطار", "غداء", "عشاء"]:
            bucket = by_type[mtype]
            if day - 1 >= len(bucket):
                continue
            m = bucket[day - 1]
            slot_en = SLOT_EN.get(mtype, "meal")
            planned.append(PlannedMeal(
                recipe_id=m["recipe_id"],   recipe_name=m["recipe_name"],
                meal_type=mtype,            day=day,         slot=slot_en,
                ingredients=m["ingredients"],
                cost_egp=m["cost"],         calories=m["calories"],
                protein_g=m["protein"],     carbs_g=m["carbs"],
                fats_g=m["fats"],           prep_time=m["prep_time"],
            ))
            days_dict[day].append({"slot": slot_en, "recipe_name": m["recipe_name"],
                "cost_egp": m["cost"], "calories": m["calories"], "protein_g": m["protein"]})

    return planned, dict(days_dict)


async def optimize_meal_plan(req: MealPlanRequest, db: AsyncSession, user=None) -> MealPlanResponse:
    recipes = await _load_priced_recipes(db, source_filter=req.source)
    if not recipes:
        return MealPlanResponse(status="infeasible", plan_type=req.plan_type,
            total_cost_egp=0, total_calories=0, total_protein_g=0,
            total_carbs_g=0, total_fats_g=0, total_meals=0, meals=[],
            solve_time_ms=0, solver_message="No recipes found. Upload meals dataset first.",
            budget_used_pct=0, calories_met=False, protein_met=False)

    if user:
        forbidden = json.loads(user.forbidden_foods or "[]") if isinstance(user.forbidden_foods, str) else (user.forbidden_foods or [])
        allergies = json.loads(user.allergies       or "[]") if isinstance(user.allergies,       str) else (user.allergies       or [])
        forbidden_lower = {f.lower().strip() for f in forbidden}
        allergy_map = {
            "lactose": {"milk","cream","cheese","butter","yogurt","dairy","mozzarella"},
            "gluten":  {"flour","bread","pasta","wheat","spaghetti","macaroni"},
            "nuts":    {"peanut","walnut","almond","pistachio","cashew"},
            "seafood": {"fish","shrimp","calamari","squid","tuna","sardine"},
            "eggs":    {"egg","eggs"},
        }
        blocked = set()
        for a in allergies:
            blocked.update(allergy_map.get(a.lower(), {a.lower()}))

        before  = len(recipes)
        recipes = [r for r in recipes
            if not any(f in r["recipe_name"].lower() for f in forbidden_lower)
            and not any(any(b in str(i.get("name","")).lower() for b in (forbidden_lower|blocked))
                        for i in r.get("ingredients",[]))]
        if before - len(recipes):
            logger.info(f"🚫 Filtered {before-len(recipes)} recipes (restrictions)")

        if not recipes:
            return MealPlanResponse(status="infeasible", plan_type=req.plan_type,
                total_cost_egp=0, total_calories=0, total_protein_g=0,
                total_carbs_g=0, total_fats_g=0, total_meals=0, meals=[],
                solve_time_ms=0, solver_message="No recipes after food restrictions.",
                budget_used_pct=0, calories_met=False, protein_met=False)

    # ── Hybrid MILP + Collaborative Filtering ────────────────────────────────
    # Load user's liked meals → boost those recipes in the MILP objective
    if user:
        try:
            # Use a fresh query — don't let failures pollute the main session
            # Check user_interactions first, fallback to user_feedback
            liked_result = await db.execute(text("""
                SELECT LOWER(recipe_name) as name
                FROM (
                    SELECT recipe_name, created_at FROM user_interactions
                    WHERE user_id = :uid AND interaction_type = 'liked'
                    UNION ALL
                    SELECT recipe_name, created_at FROM user_feedback
                    WHERE user_id = :uid AND interaction_type = 'liked'
                ) combined
                ORDER BY created_at DESC LIMIT 50
            """), {"uid": user.id})
            liked_rows  = liked_result.fetchall()
            liked_names = {r.name for r in liked_rows} if liked_rows else set()

            if liked_names:
                CF_BOOST  = 0.15  # reduce effective cost by 15% for liked recipes
                cf_count  = 0
                for r in recipes:
                    name_lower = r["recipe_name"].lower()
                    if any(liked in name_lower or name_lower in liked
                           for liked in liked_names):
                        r["cost_egp"]      = max(0.1, r["cost_egp"] * (1 - CF_BOOST))
                        r["is_cf_boosted"] = True
                        cf_count += 1

                if cf_count:
                    logger.info(f"🤝 CF Hybrid: boosted {cf_count} liked recipes")

        except Exception as e:
            # Non-critical: if user_interactions table missing or any error,
            # just skip CF boost and continue with normal optimization
            logger.debug(f"CF boost skipped: {e}")
            await db.rollback()  # clean up session state

    result = _solve(recipes, req)
    if result["status"] == "infeasible":
        return MealPlanResponse(status="infeasible", plan_type=req.plan_type,
            total_cost_egp=0, total_calories=0, total_protein_g=0,
            total_carbs_g=0, total_fats_g=0, total_meals=0, meals=[],
            solve_time_ms=result.get("solve_time_ms",0),
            solver_message=result.get("reason","Infeasible"),
            budget_used_pct=0, calories_met=False, protein_met=False)

    planned, days_dict = _assign_slots(result["selected"], req.plan_type)
    return MealPlanResponse(
        status=result["status"],              plan_type=req.plan_type,
        total_cost_egp=result["total_cost"],  total_calories=result["total_calories"],
        total_protein_g=result["total_protein"], total_carbs_g=result["total_carbs"],
        total_fats_g=result["total_fats"],    total_meals=len(planned),
        meals=planned,                         solve_time_ms=result["solve_time_ms"],
        solver_message=result["solver_message"],
        budget_used_pct=result["budget_used_pct"],
        calories_met=result["calories_met"],  protein_met=result["protein_met"],
        days=days_dict or None,
    )