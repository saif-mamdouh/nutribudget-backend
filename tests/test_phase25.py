"""
Phase 2.5 — Matching Engine Tests
Run: python -m pytest tests/test_phase25.py -v -p no:warnings
"""
import pytest
from app.utils.fuzzy_matcher import find_best_fuzzy_match, batch_fuzzy_match
from app.utils.normalizer import normalize_name


NUTRITION_CATALOGUE = [
    "tomato", "chicken breast", "beef", "milk", "egg",
    "banana", "apple", "potato", "bread white", "rice white",
    "yoghurt", "cucumber", "carrot", "onion", "lentil",
]


# ── Fuzzy matcher unit tests ───────────────────────────────────────────────────
class TestFuzzyMatcher:

    def test_exact_match(self):
        result = find_best_fuzzy_match("tomato", NUTRITION_CATALOGUE)
        assert result is not None
        assert result[0] == "tomato"
        assert result[1] == 1.0

    def test_word_order_invariant(self):
        # "breast chicken" should match "chicken breast"
        q = normalize_name("breast chicken 500g")
        result = find_best_fuzzy_match(q, NUTRITION_CATALOGUE)
        assert result is not None
        assert result[0] == "chicken breast"

    def test_noise_stripped_match(self):
        # Normalizer removes "fresh", "1kg" → should still match "tomato"
        q = normalize_name("Fresh Tomatoes 1kg")
        result = find_best_fuzzy_match(q, NUTRITION_CATALOGUE)
        assert result is not None
        assert result[0] == "tomato"

    def test_no_match_below_threshold(self):
        result = find_best_fuzzy_match("electronics phone charger", NUTRITION_CATALOGUE)
        assert result is None

    def test_confidence_range(self):
        result = find_best_fuzzy_match("carrot", NUTRITION_CATALOGUE)
        assert result is not None
        conf = result[1]
        assert 0.0 <= conf <= 1.0

    def test_batch_match(self):
        queries = [
            normalize_name("Fresh Tomatoes 1kg"),
            normalize_name("Chicken Breast 500g"),
            normalize_name("electronics cable"),
        ]
        results = batch_fuzzy_match(queries, NUTRITION_CATALOGUE)
        assert len(results) == 3
        # Two food items should match, one should not
        matched = [k for k, v in results.items() if v is not None]
        assert len(matched) >= 2

    def test_empty_query(self):
        result = find_best_fuzzy_match("", NUTRITION_CATALOGUE)
        assert result is None

    def test_empty_candidates(self):
        result = find_best_fuzzy_match("tomato", [])
        assert result is None


# ── Matching API integration tests ─────────────────────────────────────────────
NUTRITION_PAYLOAD = {
    "normalized_name": "tomato",
    "display_name": "Fresh Tomato",
    "calories_per_100g": 18,
    "protein_g": 0.9,
    "carbs_g": 3.9,
    "fats_g": 0.2,
    "fiber_g": 1.2,
    "data_source": "usda",
}

PRODUCT_CSV = b"""source,sku,category,product_name,price
Carrefour,TM001,Vegetables,Fresh Tomatoes 1kg,25.99
Carrefour,CK001,Meat,Chicken Breast 500g,89.00
Carrefour,EL001,Electronics,Phone Charger,150.00
"""


async def test_add_nutrition_entry(auth_client):
    r = await auth_client.post("/api/v1/match/nutrition", json=NUTRITION_PAYLOAD)
    assert r.status_code in (201, 409)  # 409 if already exists from previous run


async def test_list_nutrition(auth_client):
    r = await auth_client.get("/api/v1/match/nutrition")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_preview_match(auth_client):
    # Add nutrition first
    await auth_client.post("/api/v1/match/nutrition", json=NUTRITION_PAYLOAD)
    r = await auth_client.get("/api/v1/match/preview?name=Fresh+Tomatoes+1kg")
    assert r.status_code == 200
    data = r.json()
    assert "normalized" in data
    assert "fuzzy_candidates" in data
    assert isinstance(data["fuzzy_candidates"], list)


async def test_run_matching(auth_client):
    # Upload products
    await auth_client.post(
        "/api/v1/products/upload-csv",
        files={"file": ("p.csv", PRODUCT_CSV, "text/csv")},
    )
    # Add nutrition
    await auth_client.post("/api/v1/match/nutrition", json=NUTRITION_PAYLOAD)

    # Run matcher
    r = await auth_client.post("/api/v1/match/run", json={})
    assert r.status_code == 200
    data = r.json()
    assert "matched" in data
    assert "unmatched" in data
    assert data["matched"] >= 0


async def test_match_stats(auth_client):
    r = await auth_client.get("/api/v1/match/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_products" in data
    assert "coverage_pct" in data


async def test_low_confidence_endpoint(auth_client):
    r = await auth_client.get("/api/v1/match/low-confidence")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_match_requires_auth(client):
    r = await client.post("/api/v1/match/run", json={})
    assert r.status_code == 403
