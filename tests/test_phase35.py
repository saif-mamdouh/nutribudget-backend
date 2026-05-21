"""
Phase 3.5 — AI Personalization Tests
Run: python -m pytest tests/test_phase35.py -v -p no:warnings
"""
import pytest

# ── Seed data (reused from Phase 3) ──────────────────────────────────────────
NUTRITION_ENTRIES = [
    {"normalized_name": "chicken breast", "display_name": "Chicken Breast",
     "calories_per_100g": 165, "protein_g": 31.0, "carbs_g": 0.0, "fats_g": 3.6, "fiber_g": 0},
    {"normalized_name": "rice white", "display_name": "White Rice",
     "calories_per_100g": 130, "protein_g": 2.7, "carbs_g": 28.0, "fats_g": 0.3, "fiber_g": 0.4},
    {"normalized_name": "egg", "display_name": "Egg",
     "calories_per_100g": 155, "protein_g": 13.0, "carbs_g": 1.1, "fats_g": 11.0, "fiber_g": 0},
    {"normalized_name": "lentil", "display_name": "Lentils",
     "calories_per_100g": 116, "protein_g": 9.0, "carbs_g": 20.0, "fats_g": 0.4, "fiber_g": 7.9},
    {"normalized_name": "milk", "display_name": "Milk",
     "calories_per_100g": 61, "protein_g": 3.2, "carbs_g": 4.8, "fats_g": 3.3, "fiber_g": 0},
    {"normalized_name": "bread white", "display_name": "White Bread",
     "calories_per_100g": 265, "protein_g": 9.0, "carbs_g": 49.0, "fats_g": 3.2, "fiber_g": 2.7},
]

PRODUCT_CSV = b"""source,sku,category,product_name,price
Carrefour,PS001,Meat,Chicken Breast 500g,89.00
Carrefour,PS002,Grains,White Rice 1kg,25.00
Carrefour,PS003,Dairy,Eggs 30pcs,115.00
Carrefour,PS004,Legumes,Red Lentils 500g,22.00
Carrefour,PS005,Dairy,Full Cream Milk 1L,32.00
Carrefour,PS006,Bakery,White Bread Loaf,18.00
"""

PLAN_REQUEST = {
    "budget_egp": 300,
    "calories": 1800,
    "protein_g": 60,
    "diversity_boost": 0.2,
    "avoid_repeated": True,
}


async def _seed(auth_client):
    """Upload products, nutrition, run matching."""
    await auth_client.post(
        "/api/v1/products/upload-csv",
        files={"file": ("p.csv", PRODUCT_CSV, "text/csv")},
    )
    for entry in NUTRITION_ENTRIES:
        await auth_client.post("/api/v1/match/nutrition", json=entry)
    await auth_client.post("/api/v1/match/run", json={"force_rematch": True})


# ── Auth guard ─────────────────────────────────────────────────────────────────
async def test_personalize_requires_auth(client):
    r = await client.post("/api/v1/personalize/plan", json=PLAN_REQUEST)
    assert r.status_code == 403


# ── Preference profile (cold start) ──────────────────────────────────────────
async def test_preference_profile_cold_start(auth_client):
    """New user with no history should have empty profile."""
    r = await auth_client.get("/api/v1/personalize/profile")
    assert r.status_code == 200
    data = r.json()
    assert data["plans_in_history"] == 0
    assert data["personalization_active"] is False


# ── Personalized plan ─────────────────────────────────────────────────────────
async def test_personalized_plan_structure(auth_client):
    """Plan response must have all required fields."""
    await _seed(auth_client)
    r = await auth_client.post("/api/v1/personalize/plan", json=PLAN_REQUEST)
    assert r.status_code == 200
    data = r.json()
    assert "plan_id" in data
    assert "status" in data
    assert "items" in data
    assert "personalization" in data
    assert "solve_time_ms" in data
    assert data["plan_id"] > 0


async def test_personalized_plan_budget_respected(auth_client):
    """Personalized plan must stay within budget."""
    await _seed(auth_client)
    budget = 250.0
    r = await auth_client.post("/api/v1/personalize/plan", json={
        **PLAN_REQUEST, "budget_egp": budget
    })
    assert r.status_code == 200
    data = r.json()
    if data["status"] in ("optimal", "feasible"):
        assert data["total_cost_egp"] <= budget * 1.01


async def test_personalized_plan_saved_to_history(auth_client):
    """Plan should appear in history after generation."""
    await _seed(auth_client)
    gen = await auth_client.post("/api/v1/personalize/plan", json=PLAN_REQUEST)
    plan_id = gen.json()["plan_id"]

    hist = await auth_client.get("/api/v1/personalize/history")
    assert hist.status_code == 200
    ids = [p["plan_id"] for p in hist.json()]
    assert plan_id in ids


# ── Feedback ──────────────────────────────────────────────────────────────────
async def test_submit_feedback(auth_client):
    """Feedback submission should succeed and return feedback_id."""
    await _seed(auth_client)
    gen = await auth_client.post("/api/v1/personalize/plan", json=PLAN_REQUEST)
    plan_id = gen.json()["plan_id"]

    r = await auth_client.post("/api/v1/personalize/feedback", json={
        "plan_id": plan_id,
        "rating": 4,
        "liked_items": [],
        "notes": "Good plan!",
    })
    assert r.status_code == 201
    data = r.json()
    assert "feedback_id" in data
    assert data["feedback_id"] > 0


async def test_preference_profile_after_feedback(auth_client):
    """Profile should show history after submitting feedback."""
    await _seed(auth_client)
    gen = await auth_client.post("/api/v1/personalize/plan", json=PLAN_REQUEST)
    plan_id = gen.json()["plan_id"]

    await auth_client.post("/api/v1/personalize/feedback", json={
        "plan_id": plan_id, "rating": 5, "liked_items": []
    })

    r = await auth_client.get("/api/v1/personalize/profile")
    assert r.status_code == 200
    data = r.json()
    assert data["plans_in_history"] >= 1
    assert data["personalization_active"] is True


async def test_second_plan_uses_feedback(auth_client):
    """Second plan after feedback should reflect personalization metadata."""
    await _seed(auth_client)

    # First plan
    gen1 = await auth_client.post("/api/v1/personalize/plan", json=PLAN_REQUEST)
    plan_id = gen1.json()["plan_id"]

    # Submit feedback
    await auth_client.post("/api/v1/personalize/feedback", json={
        "plan_id": plan_id, "rating": 2, "liked_items": []
    })

    # Second plan — should have personalization applied
    gen2 = await auth_client.post("/api/v1/personalize/plan", json=PLAN_REQUEST)
    assert gen2.status_code == 200
    meta = gen2.json()["personalization"]
    assert meta["history_plans_used"] >= 1


# ── History ───────────────────────────────────────────────────────────────────
async def test_history_returns_list(auth_client):
    r = await auth_client.get("/api/v1/personalize/history")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_history_limit(auth_client):
    r = await auth_client.get("/api/v1/personalize/history?limit=2")
    assert r.status_code == 200
    assert len(r.json()) <= 2


# ── Weekly plan ───────────────────────────────────────────────────────────────
async def test_weekly_personalized_plan(auth_client):
    """Weekly plan period should be 'weekly'."""
    await _seed(auth_client)
    r = await auth_client.post("/api/v1/personalize/plan", json={
        **PLAN_REQUEST, "weekly_plan": True
    })
    assert r.status_code == 200
    assert r.json()["period"] == "weekly"
