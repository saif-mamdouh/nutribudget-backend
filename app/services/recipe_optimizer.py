"""
recipe_optimizer.py
═══════════════════
MILP-based per-recipe product selection using PuLP + CBC.

For each ingredient in a recipe (e.g. "rice", "lentils") we choose:
  • one product (brand) from the available pool, AND
  • the weight in grams of that product (within ±15% of the recipe target,
    when a budget allows the optimizer to flex)

OBJECTIVE
─────────
- No budget               → Minimize cost, weight pinned to target.
- Budget given (feasible) → Maximize cost + ε·protein  s.t.  cost ≤ budget.
                            Weight free in [0.85·target, 1.15·target].
                            (Cost is the primary signal of "premium-ness";
                             ε·protein breaks ties between equally-priced
                             selections in favor of higher protein.)
- Budget infeasible       → Fallback: Minimize cost (with flex).
                            Returns budget_exceeded=True so the caller can
                            tell the user "your budget was too low".

DESIGN NOTES
────────────
- Weight is `wg = recipe_target_g`. The optimizer is allowed to scale
  by ±15% only when there is a budget — otherwise the recipe portions
  stay intact.
- One brand per ingredient: linked via a binary `select` variable so we
  never get a "blend" of two brands for the same ingredient.
- ε for the protein tiebreaker is 0.01 EGP/g_protein. Small enough that
  cost dominates (a 1 EGP cost difference outweighs 100g protein), but
  large enough to break ties when two products cost the same.
"""

from __future__ import annotations

import logging
from typing import Optional

try:
    import pulp
except ImportError as e:           # pragma: no cover
    raise ImportError(
        "PuLP is required for recipe_optimizer. Install with: pip install pulp"
    ) from e

logger = logging.getLogger("nutribudget.recipe_optimizer")

# ── Tunable constants ────────────────────────────────────────────────────────
WEIGHT_FLEX_PCT          = 0.15   # ±15% weight flexibility (only when budget)
PROTEIN_TIEBREAK_WEIGHT  = 0.01   # ε in: max( cost + ε·protein )
SOLVER_TIMEOUT_SEC       = 2      # CBC time-limit per recipe (per solve)

# When an ingredient has both real (scraped) and "Estimated" options, prefer
# real — Estimated rows often have placeholder prices that are unrealistically
# cheap (e.g. eggs at 0.38 EGP/100g). Apply a large penalty per estimated
# brand selection so the solver picks a real brand whenever one is available,
# but still falls back to Estimated when that's the only option.
#
# The penalty must dominate any plausible price-per-100g difference between
# real and estimated brands of the same ingredient. Real-vs-est gaps in our
# data are at most ~10 EGP/100g × 200g = 2 000 EGP per ingredient in the
# pathological case, but realistic recipes are well under 100 EGP per item.
# 1000 EGP is a safe ceiling that still doesn't overflow CBC's numerics.
EST_PENALTY_EGP          = 1000.0  # virtual cost added per estimated brand selection


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def optimize_recipe(
    ingredients: list[dict],
    products_map: dict[str, list[dict]],
    budget: Optional[float] = None,
) -> dict:
    """
    Pick one product (and its weight) per ingredient, minimising or
    maximising cost subject to budget.

    Parameters
    ----------
    ingredients : list of {"name": str, "weight_g": float}
        Recipe lines, e.g. [{"name":"rice","weight_g":100}, ...].
    products_map : dict[str, list[product_dict]]
        For each ingredient_key, the list of available products. Each
        product is a dict with keys: price_per_100g, price_egp, unit_weight_g,
        calories, protein, carbs, fats, product_name, source, display_name.
    budget : float | None
        Total recipe budget in EGP. None → minimise cost.

    Returns
    -------
    dict with:
        status            : "optimal" | "infeasible" | "no_data"
        total_cost        : float (EGP)
        total_protein     : float (g)
        total_calories    : float (kcal)
        total_carbs       : float (g)
        total_fats        : float (g)
        budget_exceeded   : bool — True iff budget was too low and we fell
                            back to Minimize.
        selected          : list of dicts (one per matched ingredient) with
                            product_name, weight_g, cost_egp, etc.
        unmatched         : list of ingredient_keys with no product mapping.
    """
    # 1. Partition ingredients into matched (have products) vs unmatched
    valid: list[tuple[str, float, list[dict]]] = []
    unmatched: list[str] = []

    for ing in ingredients:
        key = ing.get("name", "")
        wg  = float(ing.get("weight_g", 0) or 0)
        if wg <= 0:
            continue
        opts = products_map.get(key) or []
        if opts:
            valid.append((key, wg, opts))
        else:
            unmatched.append(key)

    empty_result = {
        "status":          "no_data",
        "total_cost":      0.0,
        "total_protein":   0.0,
        "total_calories":  0.0,
        "total_carbs":     0.0,
        "total_fats":      0.0,
        "budget_exceeded": False,
        "selected":        [],
        "unmatched":       unmatched,
    }
    if not valid:
        return empty_result

    has_budget = budget is not None and float(budget) > 0
    budget_val = float(budget) if has_budget else None

    # 2. Choose strategy and solve.
    #    - No budget         → Minimize, no flex   (recipe portions intact).
    #    - With budget       → Maximize, ±15% flex, cost ≤ budget.
    #    - Maximize infeasible → Fallback Minimize with ±15% flex
    #                           (try to squeeze under budget).
    #    - Still infeasible  → Last-resort Minimize with no flex.
    budget_exceeded = False

    if has_budget:
        sol = _solve(
            valid,
            maximize=True,
            budget_cap=budget_val,
            flex=WEIGHT_FLEX_PCT,
        )
        if sol is None:
            logger.info(
                "Recipe budget %.2f EGP infeasible — falling back to Minimize",
                budget_val,
            )
            budget_exceeded = True
            sol = _solve(
                valid,
                maximize=False,
                budget_cap=None,
                flex=WEIGHT_FLEX_PCT,
            )
            if sol is None:
                # Give up the flex — solve at exact target weights
                sol = _solve(valid, maximize=False, budget_cap=None, flex=0.0)
    else:
        sol = _solve(valid, maximize=False, budget_cap=None, flex=0.0)

    if sol is None:
        return {**empty_result, "status": "infeasible",
                "budget_exceeded": budget_exceeded}

    # 3. Translate raw PuLP variables into a clean response.
    selected, totals = _materialise(sol, valid)

    return {
        "status":          "optimal",
        "total_cost":      round(totals["cost"], 2),
        "total_protein":   round(totals["protein"], 2),
        "total_calories":  round(totals["calories"], 1),
        "total_carbs":     round(totals["carbs"], 2),
        "total_fats":      round(totals["fats"], 2),
        "budget_exceeded": budget_exceeded,
        "selected":        selected,
        "unmatched":       unmatched,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────
def _solve(
    valid: list[tuple[str, float, list[dict]]],
    maximize: bool,
    budget_cap: Optional[float],
    flex: float,
) -> Optional[dict]:
    """
    Build & solve one MILP. Returns dict with raw vars + objective values,
    or None if the problem is infeasible / errors out.
    """
    sense = pulp.LpMaximize if maximize else pulp.LpMinimize
    prob  = pulp.LpProblem("recipe_pick", sense)

    y: dict[tuple[int, int], pulp.LpVariable] = {}  # binary: select brand p for ingredient i
    x: dict[tuple[int, int], pulp.LpVariable] = {}  # continuous: grams used of (i,p)

    cost_terms:    list = []
    protein_terms: list = []
    est_terms:     list = []   # virtual penalty terms to break ties toward real brands

    for i_idx, (key, target_w, opts) in enumerate(valid):
        select_for_i = []

        # Only apply the estimation penalty if this ingredient has at least one
        # real (non-estimated) option AND at least one estimated option.
        # If all options are estimated, the penalty is identical for every
        # choice and only changes the absolute objective value, not the choice.
        has_real = any(not p.get("is_estimated", False) for p in opts)
        has_est  = any(    p.get("is_estimated", False) for p in opts)
        apply_est_penalty = has_real and has_est

        for p_idx, p in enumerate(opts):
            ppg  = max(0.0, float(p.get("price_per_100g", 0) or 0))
            prot = max(0.0, float(p.get("protein",        0) or 0))
            est  = bool(p.get("is_estimated", False))

            yvar = pulp.LpVariable(f"y_{i_idx}_{p_idx}", cat="Binary")
            xvar = pulp.LpVariable(f"x_{i_idx}_{p_idx}", lowBound=0)

            y[(i_idx, p_idx)] = yvar
            x[(i_idx, p_idx)] = xvar

            # Linking: weight is zero unless this brand is selected
            if flex <= 0:
                prob += xvar == target_w * yvar, f"weq_{i_idx}_{p_idx}"
            else:
                w_min = (1 - flex) * target_w
                w_max = (1 + flex) * target_w
                prob += xvar >= w_min * yvar, f"wmin_{i_idx}_{p_idx}"
                prob += xvar <= w_max * yvar, f"wmax_{i_idx}_{p_idx}"

            select_for_i.append(yvar)
            cost_terms.append((ppg / 100.0) * xvar)
            protein_terms.append((prot / 100.0) * xvar)
            if apply_est_penalty and est:
                est_terms.append(EST_PENALTY_EGP * yvar)

        # Exactly one brand per ingredient
        prob += pulp.lpSum(select_for_i) == 1, f"one_brand_{i_idx}"

    total_cost    = pulp.lpSum(cost_terms)
    total_protein = pulp.lpSum(protein_terms)
    total_est_pen = pulp.lpSum(est_terms) if est_terms else 0

    if maximize:
        # Maximize cost+protein, but subtract est penalty (we still don't WANT
        # estimated picks even when we're trying to spend more).
        prob += total_cost + PROTEIN_TIEBREAK_WEIGHT * total_protein - total_est_pen
    else:
        # Minimize cost + est penalty (penalty becomes a tiebreaker against est).
        prob += total_cost + total_est_pen

    if budget_cap is not None:
        # The budget constraint is on the *real* cost, not the penalised one.
        prob += total_cost <= budget_cap, "budget"

    # Solve with CBC, silent
    try:
        solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=SOLVER_TIMEOUT_SEC)
        prob.solve(solver)
    except Exception as e:                    # pragma: no cover
        logger.warning("PuLP solve crashed: %s", e)
        return None

    status = pulp.LpStatus.get(prob.status, "Unknown")
    if status != "Optimal":
        logger.debug("MILP status: %s (maximize=%s, flex=%.2f)",
                     status, maximize, flex)
        return None

    return {
        "y":             y,
        "x":             x,
        "total_cost":    pulp.value(total_cost) or 0.0,
        "total_protein": pulp.value(total_protein) or 0.0,
    }


def _materialise(
    sol: dict,
    valid: list[tuple[str, float, list[dict]]],
) -> tuple[list[dict], dict[str, float]]:
    """Read PuLP variable values back into a clean per-ingredient list."""
    selected: list[dict] = []
    totals = {"cost": 0.0, "protein": 0.0, "calories": 0.0,
              "carbs": 0.0, "fats": 0.0}

    for i_idx, (key, target_w, opts) in enumerate(valid):
        chosen_p   = None
        chosen_w   = 0.0
        chosen_idx = -1

        for p_idx, p in enumerate(opts):
            yval = pulp.value(sol["y"].get((i_idx, p_idx)))
            if yval is not None and yval > 0.5:
                chosen_p   = p
                chosen_w   = pulp.value(sol["x"].get((i_idx, p_idx))) or 0.0
                chosen_idx = p_idx
                break

        if chosen_p is None or chosen_w <= 0:
            continue

        ppg     = float(chosen_p.get("price_per_100g", 0) or 0)
        cal100  = float(chosen_p.get("calories",       0) or 0)
        prot100 = float(chosen_p.get("protein",        0) or 0)
        carb100 = float(chosen_p.get("carbs",          0) or 0)
        fat100  = float(chosen_p.get("fats",           0) or 0)

        cost  = (ppg     / 100.0) * chosen_w
        cal   = (cal100  / 100.0) * chosen_w
        prot  = (prot100 / 100.0) * chosen_w
        carbs = (carb100 / 100.0) * chosen_w
        fats  = (fat100  / 100.0) * chosen_w

        totals["cost"]     += cost
        totals["protein"]  += prot
        totals["calories"] += cal
        totals["carbs"]    += carbs
        totals["fats"]     += fats

        pack_weight = float(chosen_p.get("unit_weight_g", 1000) or 1000)
        pack_price  = float(chosen_p.get("price_egp",     0)    or 0)
        pack_servs  = round(pack_weight / chosen_w, 1) if chosen_w > 0 else 0

        selected.append({
            "name":             key,
            "display_name":     chosen_p.get("display_name") or
                                key.replace("_", " ").title(),
            "product_name":     chosen_p.get("product_name", ""),
            "source":           chosen_p.get("source",       ""),
            "is_estimated":     bool(chosen_p.get("is_estimated", False)),
            "price_per_100g":   ppg,
            "weight_g":         round(chosen_w, 1),
            "weight_g_target":  round(target_w, 1),
            "weight_adjusted":  abs(chosen_w - target_w) > 0.5,
            "cost_egp":         round(cost, 2),
            "calories":         round(cal, 1),
            "protein_g":        round(prot, 2),
            "carbs_g":          round(carbs, 2),
            "fats_g":           round(fats, 2),
            "pack_price_egp":   round(pack_price, 2),
            "pack_weight_g":    pack_weight,
            "pack_servings":    pack_servs,
            "_brand_index":     chosen_idx,
        })

    return selected, totals


# ─────────────────────────────────────────────────────────────────────────────
# Smoke tests — run with: python -m app.services.recipe_optimizer
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Mock koshari pool — minimum viable products per ingredient
    KOSHARI_POOL = {
        "rice": [
            {"product_name": "Basata Egyptian Rice 1kg",        "price_per_100g": 2.5,
             "price_egp": 25,  "unit_weight_g": 1000, "calories": 365, "protein": 7.0,
             "carbs": 80, "fats": 0.6, "display_name": "أرز أبيض", "source": "Hyperone"},
            {"product_name": "El Doha Egyptian Rice 1kg",       "price_per_100g": 2.9,
             "price_egp": 29,  "unit_weight_g": 1000, "calories": 365, "protein": 7.2,
             "carbs": 80, "fats": 0.6, "display_name": "أرز أبيض", "source": "Hyperone"},
            {"product_name": "Premium Basmati 1kg",             "price_per_100g": 9.5,
             "price_egp": 95,  "unit_weight_g": 1000, "calories": 365, "protein": 8.0,
             "carbs": 78, "fats": 0.8, "display_name": "أرز أبيض", "source": "Spinneys"},
        ],
        "lentils": [
            {"product_name": "El Doha Lentils 1kg",             "price_per_100g": 3.4,
             "price_egp": 34,  "unit_weight_g": 1000, "calories": 116, "protein": 9.0,
             "carbs": 20, "fats": 0.4, "display_name": "عدس مسلوق", "source": "Hyperone"},
            {"product_name": "Premium Organic Lentils 500g",    "price_per_100g": 8.0,
             "price_egp": 40,  "unit_weight_g": 500,  "calories": 116, "protein": 9.5,
             "carbs": 20, "fats": 0.4, "display_name": "عدس مسلوق", "source": "Spinneys"},
        ],
        "pasta": [
            {"product_name": "Basata Pasta 500g",               "price_per_100g": 2.8,
             "price_egp": 14,  "unit_weight_g": 500,  "calories": 158, "protein": 5.8,
             "carbs": 31, "fats": 0.9, "display_name": "مكرونة", "source": "Hyperone"},
            {"product_name": "Italiano Pasta 500g",             "price_per_100g": 6.0,
             "price_egp": 30,  "unit_weight_g": 500,  "calories": 158, "protein": 6.2,
             "carbs": 31, "fats": 0.9, "display_name": "مكرونة", "source": "Spinneys"},
        ],
        "tomato_sauce": [
            {"product_name": "Roca Tomato Sauce 300g",          "price_per_100g": 5.2,
             "price_egp": 15.5, "unit_weight_g": 300, "calories": 32, "protein": 1.6,
             "carbs": 7,  "fats": 0.2, "display_name": "صلصة طماطم", "source": "Hyperone"},
        ],
        "fried_onion": [
            {"product_name": "Crispy Fried Onion 100g",         "price_per_100g": 35.0,
             "price_egp": 35,  "unit_weight_g": 100, "calories": 320, "protein": 8.0,
             "carbs": 30, "fats": 18, "display_name": "بصل مقلي", "source": "Hyperone"},
        ],
    }

    KOSHARI_INGS = [
        {"name": "rice",         "weight_g": 100},
        {"name": "lentils",      "weight_g": 50},
        {"name": "pasta",        "weight_g": 50},
        {"name": "tomato_sauce", "weight_g": 80},
        {"name": "fried_onion",  "weight_g": 30},
    ]

    def run(label: str, budget):
        print(f"\n══ {label} (budget={budget}) ══")
        r = optimize_recipe(KOSHARI_INGS, KOSHARI_POOL, budget=budget)
        print(f"  status          : {r['status']}")
        print(f"  total_cost      : {r['total_cost']} EGP")
        print(f"  total_protein   : {r['total_protein']} g")
        print(f"  budget_exceeded : {r['budget_exceeded']}")
        for s in r["selected"]:
            flex_tag = " (flexed)" if s["weight_adjusted"] else ""
            print(f"   • {s['name']:14s} → {s['product_name']:35s}"
                  f"  {s['weight_g']:.1f}g{flex_tag}"
                  f"  | {s['cost_egp']:.2f} EGP")

    # Test 1: no budget — cheapest brands, weight at target
    run("No budget", None)

    # Test 2: comfortable budget — should select premium brands
    run("Comfortable budget", 50.0)

    # Test 3: moderate budget — somewhere between
    run("Moderate budget", 25.0)

    # Test 4: budget too low — fallback Minimize with budget_exceeded=True
    run("Budget too low", 10.0)

    # Test 5: budget hugging the cheapest possible total
    run("Just-enough budget", 18.0)
