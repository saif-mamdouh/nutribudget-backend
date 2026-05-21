"""
services/vision.py
──────────────────
Meal image analysis using Gemini Vision (google-genai SDK) + nutrition DB.

pip install google-genai Pillow
GEMINI_API_KEY=your_key in .env
"""

import json
import logging
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.nutrition import NutritionFact
from app.models.product import Product
from app.schemas.vision import MealAnalysisResponse, MacroEstimate, IngredientEstimate
from app.utils.fuzzy_matcher import find_best_fuzzy_match
from app.utils.normalizer import normalize_name

logger = logging.getLogger("nutribudget.vision")

MAX_IMAGE_BYTES = 10 * 1024 * 1024

DEFAULT_PORTIONS: dict[str, float] = {
    "chicken": 150.0, "beef": 150.0, "fish": 150.0,
    "egg": 60.0,      "tuna": 100.0,
    "rice": 200.0,    "bread": 60.0,  "pasta": 180.0, "lentil": 150.0,
    "tomato": 100.0,  "cucumber": 80.0, "potato": 150.0,
    "carrot": 80.0,   "onion": 50.0,  "spinach": 80.0,
    "milk": 200.0,    "cheese": 40.0, "yoghurt": 150.0,
    "banana": 120.0,  "apple": 150.0, "orange": 150.0,
    "_default": 100.0,
}

NON_FOOD_LABELS = {
    "dish", "food", "cuisine", "meal", "plate", "bowl", "table",
    "restaurant", "ingredient", "recipe", "cook", "eating",
    "photography", "tableware", "cutlery", "fork", "spoon", "knife",
    "wood", "white", "background", "texture", "pattern",
}


# ── Gemini Vision call (google-genai SDK v1+) ─────────────────────────────────

def _call_gemini_vision(image_bytes: bytes, content_type: str) -> list[dict]:
    """
    Uses the new google-genai SDK (not the deprecated google-generativeai).
    Install: pip install google-genai Pillow
    """
    import os
    from google import genai
    from google.genai import types
    import PIL.Image

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not set. "
            "Get a free key from https://aistudio.google.com/app/apikey "
            "and add it to your .env file."
        )
    os.environ["GEMINI_API_KEY"] = api_key
    client = genai.Client()

    prompt = """Analyze this food image and identify all visible food items.

Return ONLY a valid JSON array (no markdown, no explanation) like this:
[
  {"label": "chicken breast", "confidence": 0.95},
  {"label": "rice",           "confidence": 0.90},
  {"label": "tomato",         "confidence": 0.80}
]

Rules:
- Include only actual food/ingredient items (not plate, table, fork, etc.)
- Use simple English names (e.g. "chicken" not "poultry")
- confidence is a float between 0.0 and 1.0
- List up to 10 items, sorted by confidence descending
- If no food is detected, return an empty array: []"""

    image = PIL.Image.open(BytesIO(image_bytes))

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[prompt, image],
    )

    raw_text = response.text.strip()

    # Strip markdown fences if present
    if raw_text.startswith("```"):
        parts = raw_text.split("```")
        raw_text = parts[1] if len(parts) > 1 else raw_text
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        labels = json.loads(raw_text)
        if not isinstance(labels, list):
            raise ValueError("Not a list")
        return [
            {
                "label":      str(item.get("label", "")).lower().strip(),
                "confidence": float(item.get("confidence", 0.5)),
            }
            for item in labels if item.get("label")
        ]
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Gemini non-JSON response: {raw_text[:200]} — {e}")
        return _parse_fallback(raw_text)


def _parse_fallback(raw_text: str) -> list[dict]:
    words = raw_text.lower().replace(",", " ").replace("\n", " ").split()
    labels = []
    for word in words:
        word = word.strip('."\'[]{}')
        if len(word) > 3 and word not in NON_FOOD_LABELS:
            labels.append({"label": word, "confidence": 0.6})
    return labels[:10]


# ── Food label filtering ──────────────────────────────────────────────────────

def _filter_food_labels(raw_labels: list[dict], min_confidence: float = 0.50) -> list[str]:
    food_labels = []
    for item in raw_labels:
        label = item["label"].strip().lower()
        conf  = item["confidence"]
        if conf < min_confidence:
            continue
        if label in NON_FOOD_LABELS:
            continue
        if len(label) < 3:
            continue
        food_labels.append(normalize_name(label))
    return food_labels


# ── Nutrition lookup ──────────────────────────────────────────────────────────

async def _lookup_nutrition(food_labels: list[str], db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(NutritionFact.normalized_name, NutritionFact.display_name,
               NutritionFact.calories_per_100g, NutritionFact.protein_g,
               NutritionFact.carbs_g, NutritionFact.fats_g)
    )
    catalogue = result.fetchall()
    if not catalogue:
        return []

    candidate_names = [r.normalized_name for r in catalogue]
    nutrition_map   = {r.normalized_name: r for r in catalogue}
    matched, seen   = [], set()

    for label in food_labels:
        match = find_best_fuzzy_match(label, candidate_names, threshold=65)
        if not match:
            continue
        best_name, confidence = match
        if best_name in seen:
            continue
        seen.add(best_name)

        nut       = nutrition_map[best_name]
        portion_g = _default_portion(best_name)

        matched.append({
            "label":        label,
            "matched_name": nut.display_name or best_name,
            "quantity_g":   portion_g,
            "confidence":   confidence / 100,
            "calories":  round(nut.calories_per_100g * portion_g / 100, 1),
            "protein_g": round(nut.protein_g * portion_g / 100, 2),
            "carbs_g":   round(nut.carbs_g   * portion_g / 100, 2),
            "fats_g":    round(nut.fats_g    * portion_g / 100, 2),
        })

    return matched


def _default_portion(food_name: str) -> float:
    for key, portion in DEFAULT_PORTIONS.items():
        if key in food_name:
            return portion
    return DEFAULT_PORTIONS["_default"]


# ── Product price matching ────────────────────────────────────────────────────

async def _match_to_products(
    matched_nutrition: list[dict], db: AsyncSession
) -> tuple[list[dict], float]:
    result = await db.execute(
        select(Product.id, Product.product_name,
               Product.normalized_name, Product.price, Product.source)
        .where(Product.price > 0)
    )
    products = result.fetchall()
    if not products:
        return [], 0.0

    candidates = [r.normalized_name or normalize_name(r.product_name) for r in products]
    prod_map   = {(r.normalized_name or normalize_name(r.product_name)): r for r in products}
    matched_products, total_cost = [], 0.0

    for item in matched_nutrition:
        query = normalize_name(item["matched_name"])
        match = find_best_fuzzy_match(query, candidates, threshold=65)
        if not match:
            continue
        best_name, conf = match
        prod = prod_map.get(best_name)
        if not prod:
            continue
        portion_cost = round(prod.price * item["quantity_g"] / 100, 2)
        total_cost  += portion_cost
        matched_products.append({
            "ingredient":       item["matched_name"],
            "product_id":       prod.id,
            "product_name":     prod.product_name,
            "price_egp":        prod.price,
            "portion_cost_egp": portion_cost,
            "source":           prod.source,
            "match_confidence": conf,
        })

    return matched_products, round(total_cost, 2)


# ── Public entry point ────────────────────────────────────────────────────────

async def analyze_meal_image(
    image_bytes: bytes,
    content_type: str,
    db: AsyncSession,
) -> MealAnalysisResponse:
    try:
        raw_labels = _call_gemini_vision(image_bytes, content_type)
    except Exception as e:
        logger.error(f"Gemini Vision API error: {e}")
        raise

    logger.info(f"🔍 Gemini returned {len(raw_labels)} labels.")
    food_labels = _filter_food_labels(raw_labels)
    logger.info(f"🥗 Food labels after filter: {food_labels}")

    if not food_labels:
        return MealAnalysisResponse(
            meal_name="Unknown meal", ingredients=[],
            estimated_macros=MacroEstimate(), confidence=0.1,
            analysis_notes="No food items detected. Try a clearer photo.",
        )

    matched_nutrition              = await _lookup_nutrition(food_labels, db)
    matched_products, total_cost   = await _match_to_products(matched_nutrition, db)

    ingredients = [
        IngredientEstimate(
            name=item["matched_name"], quantity_g=item["quantity_g"],
            calories=item["calories"], protein_g=item["protein_g"],
        )
        for item in matched_nutrition
    ]

    meal_name = ", ".join(i["matched_name"] for i in matched_nutrition[:3]) or "Mixed meal"
    avg_conf  = (
        sum(i["confidence"] for i in matched_nutrition) / len(matched_nutrition)
        if matched_nutrition else 0.1
    )

    return MealAnalysisResponse(
        meal_name=meal_name,
        ingredients=ingredients,
        estimated_macros=MacroEstimate(
            calories=round(sum(i["calories"]  for i in matched_nutrition), 1),
            protein_g=round(sum(i["protein_g"] for i in matched_nutrition), 2),
            carbs_g=round(sum(i["carbs_g"]   for i in matched_nutrition), 2),
            fats_g=round(sum(i["fats_g"]    for i in matched_nutrition), 2),
        ),
        estimated_cost_egp=total_cost,
        confidence=round(avg_conf, 3),
        analysis_notes=(
            f"Detected {len(food_labels)} food items via Gemini Vision. "
            f"Macros calculated from nutrition database. "
            f"Portions estimated using standard Egyptian serving sizes."
        ),
        matched_products=matched_products,
    )
