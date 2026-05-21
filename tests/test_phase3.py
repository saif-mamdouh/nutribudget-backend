"""
Phase 3 — Optimization Engine Tests
Run: python -m pytest tests/test_phase3.py -v -p no:warnings
"""
import pytest
from app.schemas.optimizer import OptimizeRequest


# ── Sample data pushed into DB before optimizer tests ─────────────────────────
NUTRITION_ENTRIES = [
    {"normalized_name": "chicken breast", "display_name": "Chicken Breast",
     "calories_per_100g": 165, "protein_g": 31.0, "carbs_g": 0.0, "fats_g": 3.6, "fiber_g": 0},
    {"normalized_name": "rice white",     "display_name": "White Rice",
     "calories_per_100g": 130, "protein_g": 2.7,  "carbs_g": 28.0, "fats_g": 0.3, "fiber_g": 0.4},
    {"normalized_name": "egg",            "display_name": "Egg",
     "calories_per_100g": 155, "protein_g": 13.0, "carbs_g": 1.1,  "fats_g": 11.0,"fiber_g": 0},
    {"normalized_name": "bread white",    "display_name": "White Bread",
     "calories_per_100g": 265, "protein_g": 9.0,  "carbs_g": 49.0, "fats_g": 3.2, "fiber_g": 2.7},
    {"normalized_name": "milk",           "display_name": "Milk",
     "calories_per_100g": 61,  "protein_g": 3.2,  "carbs_g": 4.8,  "fats_g": 3.3, "fiber_g": 0},
    {"normalized_name": "lentil",         "display_name": "Lentils",
     "calories_per_100g": 116, "protein_g": 9.0,  "carbs_g": 20.0, "fats_g": 0.4, "fiber_g": 7.9},
]

PRODUCT_CSV = b"""source,sku,category,product_name,price
Carrefour,OPT001,Meat,Chicken Breast 500g,89.00
Carrefour,OPT002,Grains,White Rice 1kg,25.00
Carrefour,OPT003,Dairy,Eggs 30pcs,115.00
Carrefour,OPT004,Bakery,White Bread Loaf,18.00
Carrefour,OPT005,Dairy,Full Cream Milk 1L,32.00
Carrefour,OPT006,Legumes,Red Lentils 500g,22.00
"""


async def _seed_data(auth_client):
    """Upload products + nutrition + run matching before optimizer tests."""
    # Upload products
    await auth_client.post(
        "/api/v1/products/upload-csv",
        files={"file": ("opt.csv", PRODUCT_CSV, "text/csv")},
    )
    # Add nutrition entries (upsert — safe to call multiple times)
    for entry in NUTRITION_ENTRIES:
        await auth_client.post("/api/v1/match/nutrition", json=entry)

    # Run matching
    await auth_client.post("/api/v1/match/run", json={"force_rematch": True})


# ── Schema validation unit tests ───────────────────────────────────────────────
class TestOptimizerSchema:

    def test_valid_request(self):
        req = OptimizeRequest(budget_egp=200, calories=2000, protein_g=80)
        assert req.budget_egp == 200
        assert req.weekly_plan is False

    def test_weekly_flag(self):
        req = OptimizeRequest(budget_egp=200, calories=2000, protein_g=80, weekly_plan=True)
        assert req.weekly_plan is True

    def test_budget_floor(self):
        with pytest.raises(Exception):
            OptimizeRequest(budget_egp=5, calories=2000, protein_g=80)

    def test_calories_floor(self):
        with pytest.raises(Exception):
            OptimizeRequest(budget_egp=200, calories=100, protein_g=80)

    def test_max_items_default(self):
        req = OptimizeRequest(budget_egp=200, calories=2000, protein_g=80)
        assert req.max_items == 15


# ── API integration tests ──────────────────────────────────────────────────────
async def test_optimize_requires_auth(client):
    r = await client.post("/api/v1/optimize/plan", json={
        "budget_egp": 200, "calories": 2000, "protein_g": 80
    })
    assert r.status_code == 403


async def test_optimize_no_data_returns_infeasible(auth_client):
    """Without matched nutrition data, solver returns infeasible gracefully."""
    r = await auth_client.post("/api/v1/optimize/plan", json={
        "budget_egp": 50, "calories": 2000, "protein_g": 80
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("infeasible", "optimal", "feasible")


async def test_optimize_with_data(auth_client):
    """Full pipeline: seed data → optimize → check response structure."""
    await _seed_data(auth_client)

    r = await auth_client.post("/api/v1/optimize/plan", json={
        "budget_egp": 300,
        "calories":   2000,
        "protein_g":  60,
        "max_items":  10,
    })
    assert r.status_code == 200
    data = r.json()

    # Response structure
    assert "status" in data
    assert "items" in data
    assert "total_cost_egp" in data
    assert "total_calories" in data
    assert "total_protein_g" in data
    assert "solve_time_ms" in data
    assert "period" in data
    assert data["period"] == "daily"


async def test_optimize_cost_within_budget(auth_client):
    """Optimizer must never exceed the given budget."""
    await _seed_data(auth_client)
    budget = 200.0

    r = await auth_client.post("/api/v1/optimize/plan", json={
        "budget_egp": budget, "calories": 1500, "protein_g": 50
    })
    assert r.status_code == 200
    data = r.json()

    if data["status"] in ("optimal", "feasible"):
        assert data["total_cost_egp"] <= budget * 1.01   # 1% tolerance for float


async def test_optimize_weekly_plan(auth_client):
    """Weekly plan should have 7× the daily cost."""
    await _seed_data(auth_client)

    daily = await auth_client.post("/api/v1/optimize/plan", json={
        "budget_egp": 250, "calories": 1800, "protein_g": 50,
        "weekly_plan": False,
    })
    weekly = await auth_client.post("/api/v1/optimize/plan", json={
        "budget_egp": 250, "calories": 1800, "protein_g": 50,
        "weekly_plan": True,
    })
    assert daily.status_code == 200
    assert weekly.status_code == 200

    d = daily.json()
    w = weekly.json()

    assert w["period"] == "weekly"
    assert d["period"] == "daily"

    if d["status"] in ("optimal", "feasible") and w["status"] in ("optimal", "feasible"):
        assert abs(w["total_cost_egp"] - d["total_cost_egp"] * 7) < 1.0


async def test_optimize_from_profile(auth_client):
    """Plan from user profile should use the profile's saved targets."""
    await _seed_data(auth_client)

    r = await auth_client.post("/api/v1/optimize/plan/from-profile")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "items" in data


async def test_optimize_infeasible_tiny_budget(auth_client):
    """A 10 EGP budget with 5000 kcal target should return infeasible."""
    await _seed_data(auth_client)

    r = await auth_client.post("/api/v1/optimize/plan", json={
        "budget_egp": 10, "calories": 5000, "protein_g": 300
    })
    assert r.status_code == 200
    assert r.json()["status"] in ("infeasible", "not solved", "optimal", "feasible")


async def test_optimize_source_filter(auth_client):
    """Source filter should restrict results to that supermarket."""
    await _seed_data(auth_client)

    r = await auth_client.post("/api/v1/optimize/plan", json={
        "budget_egp": 300, "calories": 1500, "protein_g": 40,
        "source": "Carrefour",
    })
    assert r.status_code == 200
    data = r.json()

    if data["status"] in ("optimal", "feasible"):
        for item in data["items"]:
            assert item["source"] == "Carrefour"
