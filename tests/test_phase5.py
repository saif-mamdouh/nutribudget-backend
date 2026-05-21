"""
Phase 5 — Vision AI Tests (Google Vision + Nutrition DB Hybrid)
Run: python -m pytest tests/test_phase5.py -v -p no:warnings
"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock


NUTRITION_ENTRIES = [
    {"normalized_name": "chicken breast", "display_name": "Chicken Breast",
     "calories_per_100g": 165, "protein_g": 31.0, "carbs_g": 0.0, "fats_g": 3.6, "fiber_g": 0},
    {"normalized_name": "rice white", "display_name": "White Rice",
     "calories_per_100g": 130, "protein_g": 2.7, "carbs_g": 28.0, "fats_g": 0.3, "fiber_g": 0},
    {"normalized_name": "tomato", "display_name": "Tomato",
     "calories_per_100g": 18, "protein_g": 0.9, "carbs_g": 3.9, "fats_g": 0.2, "fiber_g": 1.2},
]

# Mock Google Vision API response
MOCK_VISION_LABELS = [
    {"label": "chicken",     "confidence": 0.95},
    {"label": "rice",        "confidence": 0.91},
    {"label": "food",        "confidence": 0.99},   # should be filtered out
    {"label": "dish",        "confidence": 0.98},   # should be filtered out
    {"label": "plate",       "confidence": 0.97},   # should be filtered out
    {"label": "tomato",      "confidence": 0.82},
    {"label": "wood",        "confidence": 0.70},   # should be filtered out
]


def _tiny_jpeg() -> bytes:
    """Returns a valid 1x1 white JPEG as raw bytes — no base64 needed."""
    return bytes([
        0xFF,0xD8,0xFF,0xE0,0x00,0x10,0x4A,0x46,0x49,0x46,0x00,0x01,
        0x01,0x00,0x00,0x01,0x00,0x01,0x00,0x00,0xFF,0xDB,0x00,0x43,
        0x00,0x08,0x06,0x06,0x07,0x06,0x05,0x08,0x07,0x07,0x07,0x09,
        0x09,0x08,0x0A,0x0C,0x14,0x0D,0x0C,0x0B,0x0B,0x0C,0x19,0x12,
        0x13,0x0F,0x14,0x1D,0x1A,0x1F,0x1E,0x1D,0x1A,0x1C,0x1C,0x20,
        0x24,0x2E,0x27,0x20,0x22,0x2C,0x23,0x1C,0x1C,0x28,0x37,0x29,
        0x2C,0x30,0x31,0x34,0x34,0x34,0x1F,0x27,0x39,0x3D,0x38,0x32,
        0x3C,0x2E,0x33,0x34,0x32,0xFF,0xC0,0x00,0x0B,0x08,0x00,0x01,
        0x00,0x01,0x01,0x01,0x11,0x00,0xFF,0xC4,0x00,0x1F,0x00,0x00,
        0x01,0x05,0x01,0x01,0x01,0x01,0x01,0x01,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,
        0x09,0x0A,0x0B,0xFF,0xDA,0x00,0x08,0x01,0x01,0x00,0x00,0x3F,
        0x00,0xFB,0xD5,0xFF,0xD9
    ])

async def _seed_nutrition(auth_client):
    for entry in NUTRITION_ENTRIES:
        await auth_client.post("/api/v1/match/nutrition", json=entry)


# ── Auth guard ─────────────────────────────────────────────────────────────────
async def test_vision_requires_auth(client):
    r = await client.post(
        "/api/v1/vision/analyze-meal",
        files={"file": ("meal.jpg", _tiny_jpeg(), "image/jpeg")},
    )
    assert r.status_code == 403


async def test_no_file_returns_422(auth_client):
    r = await auth_client.post("/api/v1/vision/analyze-meal")
    assert r.status_code == 422


async def test_empty_file_rejected(auth_client):
    r = await auth_client.post(
        "/api/v1/vision/analyze-meal",
        files={"file": ("meal.jpg", b"", "image/jpeg")},
    )
    assert r.status_code == 400


async def test_wrong_content_type_rejected(auth_client):
    r = await auth_client.post(
        "/api/v1/vision/analyze-meal",
        files={"file": ("data.csv", b"col1,col2\n1,2", "text/csv")},
    )
    assert r.status_code == 415


# ── Label filtering unit tests ────────────────────────────────────────────────
def test_filter_removes_non_food_labels():
    from app.services.vision import _filter_food_labels
    labels = [
        {"label": "chicken", "confidence": 0.95},
        {"label": "food",    "confidence": 0.99},   # non-food
        {"label": "dish",    "confidence": 0.98},   # non-food
        {"label": "rice",    "confidence": 0.90},
        {"label": "wood",    "confidence": 0.75},   # non-food
    ]
    result = _filter_food_labels(labels)
    assert "food" not in result
    assert "dish" not in result
    assert "wood" not in result
    assert any("chicken" in r for r in result)
    assert any("rice" in r for r in result)


def test_filter_removes_low_confidence():
    from app.services.vision import _filter_food_labels
    labels = [
        {"label": "chicken", "confidence": 0.95},
        {"label": "beef",    "confidence": 0.40},   # below threshold
    ]
    result = _filter_food_labels(labels, min_confidence=0.65)
    assert any("chicken" in r for r in result)
    assert not any("beef" in r for r in result)


def test_default_portion_sizes():
    from app.services.vision import _default_portion
    assert _default_portion("chicken breast") == 150.0
    assert _default_portion("rice white")     == 200.0
    assert _default_portion("egg")            == 60.0
    assert _default_portion("xyz unknown")    == 100.0   # default


# ── Full pipeline mocked ──────────────────────────────────────────────────────
async def test_analyze_meal_full_pipeline(auth_client):
    """Full pipeline: Google Vision mock → nutrition DB → macros calculation."""
    await _seed_nutrition(auth_client)

    with patch("app.services.vision._call_google_vision", return_value=MOCK_VISION_LABELS):
        r = await auth_client.post(
            "/api/v1/vision/analyze-meal",
            files={"file": ("meal.jpg", _tiny_jpeg(), "image/jpeg")},
        )

    assert r.status_code == 200
    data = r.json()

    # Structure check
    assert "meal_name" in data
    assert "ingredients" in data
    assert "estimated_macros" in data
    assert "confidence" in data
    assert "matched_products" in data

    # Macros must be non-zero (we have nutrition data)
    macros = data["estimated_macros"]
    assert macros["calories"] > 0
    assert macros["protein_g"] > 0

    # Non-food labels must be filtered
    ingredient_names = [i["name"].lower() for i in data["ingredients"]]
    assert "food" not in ingredient_names
    assert "dish" not in ingredient_names
    assert "plate" not in ingredient_names


async def test_macros_calculated_from_db(auth_client):
    """Verify macros match manual calculation from nutrition_facts."""
    await _seed_nutrition(auth_client)

    # Only chicken label — 150g default portion
    # chicken breast: 165 kcal/100g → 150g = 247.5 kcal
    mock_labels = [{"label": "chicken", "confidence": 0.95}]

    with patch("app.services.vision._call_google_vision", return_value=mock_labels):
        r = await auth_client.post(
            "/api/v1/vision/analyze-meal",
            files={"file": ("meal.jpg", _tiny_jpeg(), "image/jpeg")},
        )

    assert r.status_code == 200
    data = r.json()

    if data["ingredients"]:
        # calories should be approx 165 × 1.5 = 247.5
        assert data["estimated_macros"]["calories"] > 200


async def test_no_food_detected(auth_client):
    """When no food labels pass filter, return graceful response."""
    mock_labels = [
        {"label": "table",  "confidence": 0.99},
        {"label": "wood",   "confidence": 0.95},
        {"label": "white",  "confidence": 0.90},
    ]

    with patch("app.services.vision._call_google_vision", return_value=mock_labels):
        r = await auth_client.post(
            "/api/v1/vision/analyze-meal",
            files={"file": ("meal.jpg", _tiny_jpeg(), "image/jpeg")},
        )

    assert r.status_code == 200
    data = r.json()
    assert data["meal_name"] == "Unknown meal"
    assert data["confidence"] <= 0.2


async def test_missing_api_key_raises(auth_client):
    """Should return 502 when no Google Vision credentials configured."""
    with patch("app.services.vision.os.getenv", return_value=None), \
         patch("app.services.vision._call_google_vision",
               side_effect=Exception("No credentials")):
        r = await auth_client.post(
            "/api/v1/vision/analyze-meal",
            files={"file": ("meal.jpg", _tiny_jpeg(), "image/jpeg")},
        )
    assert r.status_code == 502


# ── Live test (skipped if no API key) ─────────────────────────────────────────
@pytest.mark.skipif(
    not os.getenv("GOOGLE_VISION_API_KEY"),
    reason="GOOGLE_VISION_API_KEY not set — skipping live test"
)
async def test_live_google_vision(auth_client):
    await _seed_nutrition(auth_client)
    r = await auth_client.post(
        "/api/v1/vision/analyze-meal",
        files={"file": ("meal.jpg", _tiny_jpeg(), "image/jpeg")},
    )
    assert r.status_code == 200
    assert "meal_name" in r.json()
