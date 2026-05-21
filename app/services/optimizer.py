"""
services/optimizer.py  (v2)
────────────────────────────
Cost formula (fixed):
  cost = (price_per_100g / 100) × weight_g_needed
"""

import logging, time
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.optimizer import OptimizeRequest, OptimizeResponse, OptimizedItem

logger = logging.getLogger("nutribudget.optimizer")


async def _load_candidate_foods(db: AsyncSession, req: OptimizeRequest) -> list[dict]:
    # Try new mapping table first
    count = (await db.execute(text("SELECT COUNT(*) FROM ingredient_product_map"))).scalar()

    if count > 0:
        sql = text("""
            SELECT
                m.ingredient_key, m.sku, m.source, m.product_name,
                m.price_per_100g, m.unit_weight_g, p.category,
                n.calories_per_100g, n.protein_g, n.carbs_g, n.fats_g
            FROM ingredient_product_map m
            JOIN nutrition_facts  n ON n.normalized_name = m.ingredient_key
            JOIN fresh_products   p ON p.sku             = m.sku
            WHERE m.price_per_100g > 0 AND n.calories_per_100g > 0
            ORDER BY m.ingredient_key, m.price_per_100g ASC
        """)
        rows = (await db.execute(sql)).fetchall()

        seen, foods = {}, []
        for r in rows:
            if req.source and r.source != req.source:
                continue
            if req.categories and r.category not in req.categories:
                continue
            if r.ingredient_key in seen:
                continue
            seen[r.ingredient_key] = True
            foods.append({
                "ingredient_key": r.ingredient_key,
                "product_id":     r.sku,
                "name":           r.product_name,
                "source":         r.source,
                "category":       r.category,
                "price":          float(r.price_per_100g),
                "unit_weight_g":  float(r.unit_weight_g or 0),
                "calories":       float(r.calories_per_100g),
                "protein":        float(r.protein_g),
                "carbs":          float(r.carbs_g),
                "fats":           float(r.fats_g),
            })
        if foods:
            logger.info(f"🥗 {len(foods)} ingredients loaded via ingredient_product_map")
            return foods

    # Fallback: legacy join (product_nutrition_map)
    from app.models.product import Product
    from app.models.nutrition import NutritionFact
    from app.models.mapping import ProductNutritionMap

    stmt = (
        select(
            Product.id, Product.product_name, Product.source,
            Product.category, Product.sku, Product.price,
            Product.unit_weight_g,
            NutritionFact.calories_per_100g, NutritionFact.protein_g,
            NutritionFact.carbs_g, NutritionFact.fats_g,
        )
        .join(ProductNutritionMap, ProductNutritionMap.product_id == Product.id)
        .join(NutritionFact, NutritionFact.id == ProductNutritionMap.nutrition_id)
        .where(ProductNutritionMap.confidence_score >= 0.75)
        .where(Product.price > 0)
    )
    if req.source:
        stmt = stmt.where(Product.source == req.source)
    if req.categories:
        stmt = stmt.where(Product.category.in_(req.categories))

    result = await db.execute(stmt)
    foods  = []
    for r in result.fetchall():
        wt   = float(r.unit_weight_g or 1000)
        p100 = round(float(r.price) / wt * 100, 4)
        if p100 <= 0 or float(r.calories_per_100g) <= 0:
            continue
        foods.append({
            "ingredient_key": str(r.id),
            "product_id":     r.sku or str(r.id),
            "name":           r.product_name,
            "source":         r.source,
            "category":       r.category,
            "price":          p100,
            "calories":       float(r.calories_per_100g),
            "protein":        float(r.protein_g),
            "carbs":          float(r.carbs_g),
            "fats":           float(r.fats_g),
        })

    logger.info(f"🥗 {len(foods)} ingredients loaded via legacy join")
    return foods


def _solve(foods: list[dict], req: OptimizeRequest) -> dict:
    """
    Multi-Objective MILP:
      minimize: cost - α×diversity_bonus - β×preference_bonus
      subject to: nutrition + budget constraints

    α = 0.5 EGP per unique food category used
    β = 0.3 EGP per ingredient from user's preferred categories
    """
    import pulp

    t0 = time.perf_counter()
    n  = len(foods)
    if n == 0:
        return {"status": "infeasible", "reason": "No candidate foods"}

    prob = pulp.LpProblem("NutriBudget_MultiObj", pulp.LpMinimize)
    q = [pulp.LpVariable(f"q_{i}", lowBound=0, upBound=req.max_quantity) for i in range(n)]
    b = [pulp.LpVariable(f"b_{i}", cat="Binary") for i in range(n)]

    # ── Category Diversity Variables ──────────────────────────────────────────
    # Binary var per unique category — 1 if at least one ingredient from it is used
    categories   = sorted(set(f["category"] for f in foods if f.get("category")))
    cat_used     = {cat: pulp.LpVariable(f"cat_{j}", cat="Binary")
                    for j, cat in enumerate(categories)}

    for j, (cat, cu) in enumerate(cat_used.items()):
        idxs = [i for i, f in enumerate(foods) if f.get("category") == cat]
        if not idxs:
            continue
        M = len(idxs)
        prob += cu <= pulp.lpSum(b[i] for i in idxs),     f"CatUpper_{j}"
        prob += M * cu >= pulp.lpSum(b[i] for i in idxs), f"CatLower_{j}"

    DIVERSITY_WEIGHT   = 0.5   # bonus per unique food category (EGP equivalent)
    PREFERENCE_WEIGHT  = 0.3   # bonus per preferred category ingredient

    # Preferred categories (high protein / fresh foods get bonus)
    PREFERRED_CATS = {"Meat & Poultry", "Vegetables & Fruits", "Dairy", "Grains & Legumes"}
    pref_bonus = pulp.lpSum(
        PREFERENCE_WEIGHT * b[i]
        for i, f in enumerate(foods)
        if f.get("category") in PREFERRED_CATS
    )

    # ── Multi-Objective: minimize cost - diversity - preference ───────────────
    prob += (
        pulp.lpSum((foods[i]["price"] / 100.0) * q[i] for i in range(n))
        - DIVERSITY_WEIGHT * pulp.lpSum(cat_used.values())
        - pref_bonus
    ), "MultiObjective"

    # ── Nutrition & Budget Constraints ────────────────────────────────────────
    prob += pulp.lpSum((foods[i]["calories"] / 100.0) * q[i] for i in range(n)) >= req.calories,  "Cal"
    prob += pulp.lpSum((foods[i]["protein"]  / 100.0) * q[i] for i in range(n)) >= req.protein_g, "Prot"
    if req.carbs_g > 0:
        prob += pulp.lpSum((foods[i]["carbs"] / 100.0) * q[i] for i in range(n)) >= req.carbs_g,  "Carbs"
    if req.fats_g > 0:
        prob += pulp.lpSum((foods[i]["fats"]  / 100.0) * q[i] for i in range(n)) >= req.fats_g,   "Fats"
    prob += pulp.lpSum((foods[i]["price"] / 100.0) * q[i] for i in range(n)) <= req.budget_egp,   "Budget"
    prob += pulp.lpSum(b[i] for i in range(n)) <= req.max_items,                                   "Items"
    for i in range(n):
        prob += q[i] <= req.max_quantity * b[i], f"UB_{i}"
        prob += q[i] >= req.min_quantity * b[i], f"LB_{i}"

    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=30))
    ms     = round((time.perf_counter() - t0) * 1000, 1)
    status = pulp.LpStatus[prob.status]

    if status not in ("Optimal", "Feasible"):
        return {"status": status.lower(), "solve_time_ms": ms,
                "reason": "Try relaxing budget or macro targets."}

    items = []
    tc = tp = tcal = tcarb = tfat = 0.0
    cats_used    = set()
    explanations = {}
    for i in range(n):
        qty = pulp.value(q[i]) or 0.0
        if qty < 1.0:
            continue
        f = foods[i]
        cats_used.add(f.get("category", ""))
        cost = (f["price"] / 100.0) * qty
        cal  = (f["calories"] / 100.0) * qty
        prot = (f["protein"]  / 100.0) * qty
        carb = (f["carbs"]    / 100.0) * qty
        fat  = (f["fats"]     / 100.0) * qty
        tc += cost; tp += prot; tcal += cal; tcarb += carb; tfat += fat
        # ── XAI: explain WHY this ingredient was chosen ─────────────────
        prot_per_egp = round(f["protein"] / max(f["price"], 0.01), 2)
        cal_pct      = round(cal / max(req.calories, 1) * 100, 1)
        if prot_per_egp >= 2.0:
            xai_text = f"مصدر ممتاز للبروتين ({prot_per_egp}g لكل EGP) · يغطي {cal_pct}% من السعرات"
        elif cal_pct >= 20:
            xai_text = f"يغطي {cal_pct}% من السعرات اليومية بتكلفة {round(cost,1)} EGP"
        elif f.get("category") in {"Vegetables & Fruits", "Vegetables"}:
            xai_text = f"مصدر أساسي للفيتامينات والألياف · {round(cal,0):.0f} kcal"
        else:
            xai_text = f"يضيف {round(prot,1)}g بروتين · {round(cal,0):.0f} kcal بـ {round(cost,1)} EGP"
        explanations[f["ingredient_key"]] = xai_text

        items.append(OptimizedItem(
            product_id=f["ingredient_key"], product_name=f["name"],
            source=f["source"], category=f["category"],
            ingredient_key=f["ingredient_key"],
            unit_weight_g=float(f.get("unit_weight_g", 0)),
            quantity_g=round(qty, 1), price_per_100g=f["price"],
            cost_egp=round(cost, 2), calories=round(cal, 1),
            protein_g=round(prot, 2), carbs_g=round(carb, 2), fats_g=round(fat, 2),
        ))

    mult = 7 if req.weekly_plan else 1
    return {
        "status":            "optimal" if status == "Optimal" else "feasible",
        "solve_time_ms":     ms,
        "items":             items,
        "total_cost_egp":    round(tc    * mult, 2),
        "total_calories":    round(tcal  * mult, 1),
        "total_protein_g":   round(tp    * mult, 2),
        "total_carbs_g":     round(tcarb * mult, 2),
        "total_fats_g":      round(tfat  * mult, 2),
        "budget_used_pct":   round(tc / req.budget_egp * 100, 1),
        "calories_met":      tcal >= req.calories  * 0.98,
        "protein_met":       tp   >= req.protein_g * 0.98,
        "period":            "weekly" if req.weekly_plan else "daily",
        "diversity_score":   len(cats_used),
        "solver_message":    f"CBC Multi-Obj: {status} in {ms}ms · {len(items)} ingredients · {len(cats_used)} categories.",
        "explanations":      explanations,
    }


async def optimize_plan(req: OptimizeRequest, db: AsyncSession) -> OptimizeResponse:
    foods = await _load_candidate_foods(db, req)
    if not foods:
        return OptimizeResponse(
            status="infeasible", total_cost_egp=0, total_calories=0,
            total_protein_g=0, total_carbs_g=0, total_fats_g=0,
            items=[], solve_time_ms=0, period="daily",
            budget_used_pct=0, calories_met=False, protein_met=False,
            solver_message="No foods found. Upload datasets first.",
        )
    result = _solve(foods, req)
    if result["status"] in ("infeasible", "not solved"):
        return OptimizeResponse(
            status=result["status"], total_cost_egp=0, total_calories=0,
            total_protein_g=0, total_carbs_g=0, total_fats_g=0,
            items=[], solve_time_ms=result.get("solve_time_ms", 0),
            period="daily", budget_used_pct=0,
            calories_met=False, protein_met=False,
            solver_message=result.get("reason", "Infeasible"),
        )
    return OptimizeResponse(**result)


# ══════════════════════════════════════════════════════════════════════════════
# Greedy Baseline — for A/B comparison with MILP
# ══════════════════════════════════════════════════════════════════════════════
def _greedy_solve(foods: list[dict], req: OptimizeRequest) -> dict:
    """
    Greedy baseline: picks ingredients by best protein-per-EGP ratio
    until calorie + protein targets are met or budget exhausted.
    Used ONLY for academic comparison with MILP.
    """
    t0 = time.perf_counter()

    if not foods:
        return {"status": "infeasible", "reason": "No candidate foods"}

    PORTION_G = 200  # fixed 200g per ingredient

    # Sort by protein/price ratio (best nutritional value per EGP)
    ranked = sorted(
        foods,
        key=lambda f: (f["protein"] / max(f["price"], 0.01)),
        reverse=True
    )

    items        = []
    tc = tp = tcal = tcarb = tfat = 0.0
    cats_used    = set()
    explanations = {}

    for f in ranked:
        if tc >= req.budget_egp:
            break
        if len(items) >= req.max_items:
            break

        qty  = PORTION_G
        cost = (f["price"]    / 100.0) * qty
        cal  = (f["calories"] / 100.0) * qty
        prot = (f["protein"]  / 100.0) * qty
        carb = (f["carbs"]    / 100.0) * qty
        fat  = (f["fats"]     / 100.0) * qty

        if tc + cost > req.budget_egp:
            continue   # skip if over budget

        tc += cost; tp += prot; tcal += cal; tcarb += carb; tfat += fat
        cats_used.add(f.get("category", ""))
        # ── XAI: explain WHY this ingredient was chosen ─────────────────
        prot_per_egp = round(f["protein"] / max(f["price"], 0.01), 2)
        cal_pct      = round(cal / max(req.calories, 1) * 100, 1)
        if prot_per_egp >= 2.0:
            xai_text = f"مصدر ممتاز للبروتين ({prot_per_egp}g لكل EGP) · يغطي {cal_pct}% من السعرات"
        elif cal_pct >= 20:
            xai_text = f"يغطي {cal_pct}% من السعرات اليومية بتكلفة {round(cost,1)} EGP"
        elif f.get("category") in {"Vegetables & Fruits", "Vegetables"}:
            xai_text = f"مصدر أساسي للفيتامينات والألياف · {round(cal,0):.0f} kcal"
        else:
            xai_text = f"يضيف {round(prot,1)}g بروتين · {round(cal,0):.0f} kcal بـ {round(cost,1)} EGP"
        explanations[f["ingredient_key"]] = xai_text
        items.append(OptimizedItem(
            product_id=f["ingredient_key"], product_name=f["name"],
            source=f["source"], category=f["category"],
            ingredient_key=f["ingredient_key"],
            unit_weight_g=float(f.get("unit_weight_g", 0)),
            quantity_g=round(qty, 1), price_per_100g=f["price"],
            cost_egp=round(cost, 2), calories=round(cal, 1),
            protein_g=round(prot, 2), carbs_g=round(carb, 2), fats_g=round(fat, 2),
        ))

    ms = round((time.perf_counter() - t0) * 1000, 1)

    return {
        "status":          "feasible",
        "solve_time_ms":   ms,
        "items":           items,
        "total_cost_egp":  round(tc,    2),
        "total_calories":  round(tcal,  1),
        "total_protein_g": round(tp,    2),
        "total_carbs_g":   round(tcarb, 2),
        "total_fats_g":    round(tfat,  2),
        "budget_used_pct": round(tc / req.budget_egp * 100, 1),
        "calories_met":    tcal >= req.calories  * 0.98,
        "protein_met":     tp   >= req.protein_g * 0.98,
        "diversity_score": len(cats_used),
        "solver_message":  f"Greedy: {len(items)} ingredients in {ms}ms · {len(cats_used)} categories.",
    }


async def compare_plans(req: OptimizeRequest, db: AsyncSession) -> dict:
    """
    Runs both MILP and Greedy on the same foods and returns comparison.
    Used for academic A/B evaluation.
    """
    foods = await _load_candidate_foods(db, req)
    if not foods:
        return {"error": "No candidate foods found"}

    milp   = _solve(foods, req)   # Full multi-objective MILP
    greedy = _greedy_solve(foods, req)

    # ── Comparison metrics ────────────────────────────────────────────────────
    milp_cost   = milp.get("total_cost_egp",  0) or 0
    greedy_cost = greedy.get("total_cost_egp", 0) or 0
    cost_saving = round(greedy_cost - milp_cost, 2)
    cost_saving_pct = round(cost_saving / greedy_cost * 100, 1) if greedy_cost > 0 else 0

    milp_cal   = milp.get("total_calories",   0) or 0
    greedy_cal = greedy.get("total_calories", 0) or 0
    milp_prot  = milp.get("total_protein_g",  0) or 0
    greedy_prot= greedy.get("total_protein_g",0) or 0

    return {
        "milp":   milp,
        "greedy": greedy,
        "comparison": {
            "cost_saving_egp":     cost_saving,
            "cost_saving_pct":     cost_saving_pct,
            "milp_wins_cost":      milp_cost   <= greedy_cost,
            "milp_wins_calories":  milp_cal    >= greedy_cal,
            "milp_wins_protein":   milp_prot   >= greedy_prot,
            "milp_wins_diversity": milp.get("diversity_score", 0) >= greedy.get("diversity_score", 0),
            "milp_calories_met":   milp.get("calories_met",  False),
            "greedy_calories_met": greedy.get("calories_met",False),
            "milp_protein_met":    milp.get("protein_met",   False),
            "greedy_protein_met":  greedy.get("protein_met", False),
            "milp_solve_ms":       milp.get("solve_time_ms",   0),
            "greedy_solve_ms":     greedy.get("solve_time_ms", 0),
            "verdict": (
                "MILP يوفّر {:.0f}% من التكلفة مع تغذية أفضل".format(cost_saving_pct)
                if cost_saving_pct > 0
                else "النتائج متقاربة في هذه الإعدادات"
            ),
        }
    }
