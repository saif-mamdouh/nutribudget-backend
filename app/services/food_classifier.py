"""
services/food_classifier.py  (YOLO VERSION)
────────────────────────────────────────────────────────────────────────────
Local YOLOv8 food classifier — no external API needed.

Pipeline:
  image → YOLOv8-cls (egyptian_food_best.pt) → class name
        → fuzzy match → recipes DB
        → macros + cost
"""
import json
import logging
from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.vision import MealAnalysisResponse, MacroEstimate, IngredientEstimate
from app.utils.fuzzy_matcher import find_best_fuzzy_match

logger = logging.getLogger("nutribudget.food_classifier")

_BASE_DIR      = Path(__file__).resolve().parent.parent.parent
MODEL_PATH     = str(_BASE_DIR / "models" / "exported" / "egyptian_food_best.pt")
CLASS_MAP_PATH = str(_BASE_DIR / "models" / "exported" / "class_map.json")

# Arabic display names for each class
CLASS_NAMES_AR = {
    "pizza":           "بيتزا",
    "burger":          "برجر",
    "pasta":           "مكرونة",
    "fried_chicken":   "فراخ مقلية",
    "steak":           "ستيك",
    "falafel":         "طعمية",
    "croissant":       "كرواسون",
    "koshari":         "كشري",
    "ful_medames":     "فول مدمس",
    "molokhia":        "ملوخية",
    "fattah":          "فتة",
    "hawawshi":        "حواوشي",
    "kofta":           "كفتة",
    "hot_dog":         "هوت دوج",
    "grilled_chicken": "فراخ مشوية",
    "pane":            "بانيه",
    "fish":            "سمك",
    "fries":           "بطاطس مقلية",
    "sushi":           "سوشي",
    "tacos":           "تاكو",
    "shawarma":        "شاورما",
    "basbosa":         "بسبوسة",
    "kunafa":          "كنافة",
    "om_ali":          "أم علي",
    "feteer":          "فطير",
}

# Direct mapping: class → exact recipe name in DB
# Run this SQL to check: SELECT DISTINCT recipe_name FROM recipes;
CLASS_TO_RECIPE = {
    "pizza":           "بيتزا",
    "burger":          "برجر",
    "pasta":           "مكرونة بالصلصة",
    "fried_chicken":   "فراخ مقلية",
    "steak":           "ستيك لحم",
    "falafel":         "طعمية",
    "croissant":       "كرواسون",
    "koshari":         "كشري",
    "ful_medames":     "فول مدمس",
    "molokhia":        "ملوخية بالأرنب",
    "fattah":          "فتة لحمة",
    "hawawshi":        "حواوشي",
    "kofta":           "كفتة",
    "hot_dog":         "هوت دوج",
    "grilled_chicken": "فراخ مشوية",
    "pane":            "بانيه دجاج",
    "fish":            "سمك",
    "fries":           "بطاطس مقلية",
    "sushi":           "سوشي",
    "tacos":           "تاكو",
    "shawarma":        " شاورما",
    "basbosa":         "بسبوسة",
    "kunafa":          "كنافة",
    "om_ali":          "أم علي",
    "feteer":          "فطير مشلتت",
}

_MODEL     = None
_IDX2CLASS = None


def _load_model():
    global _MODEL, _IDX2CLASS
    if _MODEL is not None:
        return True
    try:
        from ultralytics import YOLO
        logger.info(f"Loading YOLOv8 from: {MODEL_PATH}")
        _MODEL = YOLO(MODEL_PATH)
        with open(CLASS_MAP_PATH, encoding="utf-8") as f:
            class_map = json.load(f)
        _IDX2CLASS = {v: k for k, v in class_map.items()}
        logger.info(f"✅ Model loaded — {len(class_map)} classes")
        return True
    except Exception as e:
        logger.error(f"❌ Model load failed: {e}")
        return False


def classify_food_image(image_bytes: bytes) -> dict:
    """Classify food image — returns fallback if model not loaded yet."""
    if not _load_model():
        # Model not loaded — return fallback instead of crashing
        logger.warning("Model not loaded — returning fallback response")
        return {
            "class_name":    "unknown",
            "class_name_ar": "غير معروف",
            "confidence":    0.0,
            "error":         "Model file not found. Download from Colab and place in models/exported/"
        }

    try:
        image   = Image.open(BytesIO(image_bytes)).convert("RGB")
        results = _MODEL.predict(image, verbose=False)
        if not results or results[0].probs is None:
            return {"class_name": "unknown", "class_name_ar": "غير معروف", "confidence": 0.0}

        probs    = results[0].probs
        top1_idx = int(probs.top1)
        top1_cls = _IDX2CLASS.get(top1_idx, "unknown")
        top1_conf= float(probs.top1conf)

        # Build top-3 predictions
        top3 = []
        for idx in probs.top5[:3]:
            cls  = _IDX2CLASS.get(int(idx), "unknown")
            conf = float(probs.data[int(idx)])
            top3.append({
                "class_name":    cls,
                "class_name_ar": CLASS_NAMES_AR.get(cls, cls),
                "confidence":    round(conf, 3),
            })

        return {
            "class_name":    top1_cls,
            "class_name_ar": CLASS_NAMES_AR.get(top1_cls, top1_cls),
            "confidence":    top1_conf,
            "top3":          top3,
        }
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        return {"class_name": "unknown", "class_name_ar": "غير معروف", "confidence": 0.0}


async def get_meal_from_class(class_name, class_name_ar, confidence, top3_raw, db,
                              user=None):
    from app.schemas.vision import (
        TopPrediction, MacroFitScore, PersonalizationAdvice, MacroWarning
    )

    rows = (await db.execute(text(
        "SELECT recipe_id, recipe_name, meal_type, ingredients_json FROM recipes"
    ))).fetchall()
    if not rows:
        rows = (await db.execute(text(
            "SELECT recipe_id, recipe_name, meal_type, ingredients_json FROM egyptian_meals_dataset"
        ))).fetchall()
    if not rows:
        return _empty_response(class_name_ar or class_name, confidence, "No recipes in DB")

    recipe_names = [r.recipe_name for r in rows]
    recipe_map   = {r.recipe_name: r for r in rows}

    direct = CLASS_TO_RECIPE.get(class_name)
    match  = None
    if direct and direct in recipe_map:
        match = (direct, 100)
    if not match:
        match = find_best_fuzzy_match(class_name_ar, recipe_names, threshold=40)
    if not match:
        match = find_best_fuzzy_match(class_name, recipe_names, threshold=40)
    if not match:
        return _empty_response(
            class_name_ar, confidence,
            f"تعرفت على '{class_name_ar}' — جرب Find a Meal للبحث عنها مباشرة."
        )

    best_name, score = match
    recipe = recipe_map[best_name]
    try: ingredients = json.loads(recipe.ingredients_json)
    except: ingredients = []

    price_rows = (await db.execute(text("""
        SELECT m.ingredient_key,
               MIN(CASE WHEN fp.price>0 AND fp.unit_weight_g>0
                   THEN (fp.price/fp.unit_weight_g)*100
                   ELSE m.price_per_100g END)       AS price_per_100g,
               COALESCE(n.calories_per_100g, 0)     AS calories_per_100g,
               COALESCE(n.protein_g, 0)             AS protein_g,
               COALESCE(n.carbs_g, 0)               AS carbs_g,
               COALESCE(n.fats_g, 0)                AS fats_g
        FROM ingredient_product_map m
        LEFT JOIN nutrition_facts n ON n.normalized_name = m.ingredient_key
        LEFT JOIN fresh_products fp ON fp.sku = m.sku AND fp.source = m.source
        WHERE COALESCE(fp.price, m.price_egp) > 0
        GROUP BY m.ingredient_key, n.calories_per_100g, n.protein_g, n.carbs_g, n.fats_g
    """))).fetchall()

    pl = {r.ingredient_key: r for r in price_rows}
    tc=tp=tc2=tf=cost=0.0
    ings=[]
    for ing in ingredients:
        key=ing.get("name","").strip().lower(); wg=float(ing.get("weight_g",0))
        if wg<=0: continue
        info=pl.get(key)
        if not info: continue
        f=wg/100.0
        cost+=float(info.price_per_100g or 0)*f
        tc  +=float(info.calories_per_100g or 0)*f
        tp  +=float(info.protein_g or 0)*f
        tc2 +=float(info.carbs_g or 0)*f
        tf  +=float(info.fats_g or 0)*f
        ings.append(IngredientEstimate(name=key, quantity_g=wg,
            calories=round(float(info.calories_per_100g or 0)*f,1),
            protein_g=round(float(info.protein_g or 0)*f,2)))

    # ── Top-3 predictions ─────────────────────────────────────────────────────
    top3 = [TopPrediction(**p) for p in (top3_raw or [])]

    # ── Macro Fit Score ───────────────────────────────────────────────────────
    macro_fit    = None
    warnings     = []
    persona      = None

    if user:
        daily_cal  = float(user.daily_calories    or 2000)
        daily_prot = float(user.daily_protein_g   or 80)
        daily_carb = float(user.daily_carbs_g     or 300)
        daily_fat  = float(user.daily_fats_g      or 80)
        daily_bdg  = float(getattr(user, 'daily_budget_egp', None) or 150)

        cal_pct  = round(tc   / daily_cal  * 100, 1) if daily_cal  > 0 else 0
        prot_pct = round(tp   / daily_prot * 100, 1) if daily_prot > 0 else 0
        carb_pct = round(tc2  / daily_carb * 100, 1) if daily_carb > 0 else 0
        fat_pct  = round(tf   / daily_fat  * 100, 1) if daily_fat  > 0 else 0
        bdg_pct  = round(cost / daily_bdg  * 100, 1) if daily_bdg  > 0 else 0

        # Overall fitness (closer to 25-40% of daily = 1 meal = perfect)
        import math
        def gauss(pct, ideal=33, sigma=20):
            return round(100 * math.exp(-((pct - ideal)**2) / (2*sigma**2)), 1)

        overall = round((gauss(cal_pct)*0.35 + gauss(prot_pct)*0.40 +
                         gauss(carb_pct)*0.15 + gauss(fat_pct)*0.10), 1)

        macro_fit = MacroFitScore(
            overall_score=overall,
            calorie_pct=cal_pct, protein_pct=prot_pct,
            carbs_pct=carb_pct,  fats_pct=fat_pct, budget_pct=bdg_pct
        )

        # ── Warnings ──────────────────────────────────────────────────────────
        def warn_level(pct):
            if pct >= 80: return "danger"
            if pct >= 60: return "warning"
            return "ok"

        for wtype, pct, label in [
            ("calories", cal_pct, f"هتستهلك {cal_pct:.0f}% من سعراتك اليومية"),
            ("fats",     fat_pct, f"هتستهلك {fat_pct:.0f}% من الدهون اليومية"),
            ("carbs",    carb_pct,f"هتستهلك {carb_pct:.0f}% من الكارب اليومي"),
            ("budget",   bdg_pct, f"هتستهلك {bdg_pct:.0f}% من ميزانيتك اليومية"),
        ]:
            lvl = warn_level(pct)
            if lvl != "ok":
                warnings.append(MacroWarning(type=wtype, pct=pct, label=label, level=lvl))

        # ── Personalization ───────────────────────────────────────────────────
        GOAL_RULES = {
            "weight_loss": {
                "bad_classes":    ["pizza","burger","fries","hot_dog","kunafa","basbosa","om_ali","feteer","pasta"],
                "good_classes":   ["grilled_chicken","fish","falafel","ful_medames","koshari","molokhia","kofta","sushi","steak"],
                "bad_msg":        f"⚠️ {class_name_ar} — طريقة الطهي مش مثالية لخسارة الوزن",
                "good_msg":       f"✅ {class_name_ar} مناسب لهدف خسارة الوزن",
                "bad_suggest":    "جرب فراخ مشوية أو سمك مشوي أو سلطة خضرا بدلاً منه",
            },
            "muscle_gain": {
                "bad_classes":    ["basbosa","kunafa","om_ali","feteer","fries","tacos"],
                "good_classes":   ["grilled_chicken","steak","fish","kofta","ful_medames","hawawshi","pane"],
                "bad_msg":        f"⚠️ {class_name_ar} فيه بروتين قليل لهدف بناء العضلات",
                "good_msg":       f"✅ {class_name_ar} غني بالبروتين — مثالي لبناء العضلات",
                "bad_suggest":    "جرب ستيك أو فراخ مشوية أو بيض للحصول على بروتين أكتر",
            },
            "maintenance": {
                "bad_classes":    [],
                "good_classes":   [],
                "bad_msg":        "",
                "good_msg":       f"✅ {class_name_ar} مناسب للمحافظة على وزنك",
                "bad_suggest":    "",
            },
        }

        goal   = user.goal or "maintenance"
        rules  = GOAL_RULES.get(goal, GOAL_RULES["maintenance"])

        # Special case: fish can be fried (bad) or grilled (good)
        # Check the recipe name to determine cooking method
        recipe_lower = (recipe.recipe_name or "").lower()
        effective_class = class_name
        if class_name == "fish" and any(w in recipe_lower for w in ["مقلي", "fried", "مقلية"]):
            effective_class = "fried_fish"   # treat as bad for weight_loss

        if effective_class in rules["bad_classes"] or effective_class in ["fried_fish"] and goal == "weight_loss":
            verdict = "bad" if goal != "maintenance" else "warning"
            persona = PersonalizationAdvice(
                verdict=verdict,
                message=rules["bad_msg"],
                suggestion=rules["bad_suggest"],
            )
        elif effective_class in rules["good_classes"]:
            persona = PersonalizationAdvice(
                verdict="good",
                message=rules["good_msg"],
                suggestion="",
            )
        else:
            persona = PersonalizationAdvice(
                verdict="warning",
                message=f"🍽️ {class_name_ar} — وجبة متوازنة بشكل عام",
                suggestion="",
            )

    return MealAnalysisResponse(
        meal_name=recipe.recipe_name,
        ingredients=ings,
        estimated_macros=MacroEstimate(
            calories=round(tc,1), protein_g=round(tp,2),
            carbs_g=round(tc2,2), fats_g=round(tf,2)
        ),
        estimated_cost_egp=round(cost, 2),
        confidence=round(confidence, 3),
        analysis_notes=(
            f"تعرفت على '{class_name_ar}' ({int(confidence*100)}%). "
            f"أقرب وصفة: '{recipe.recipe_name}'."
        ),
        matched_products=[],
        top3=top3,
        macro_fit=macro_fit,
        personalization=persona,
        warnings=warnings,
    )


def _empty_response(name, conf, note):
    return MealAnalysisResponse(
        meal_name=name or "غير معروف", ingredients=[],
        estimated_macros=MacroEstimate(), confidence=conf,
        analysis_notes=note, estimated_cost_egp=0.0,
        matched_products=[], top3=[], warnings=[],
    )


async def analyze_meal_image(image_bytes, content_type, db, user=None):
    pred = classify_food_image(image_bytes)
    cls  = pred.get("class_name",    "unknown")
    ar   = pred.get("class_name_ar", "غير معروف")
    conf = float(pred.get("confidence", 0.0))
    top3 = pred.get("top3", [])
    err  = pred.get("error", "")

    logger.info(f"Vision: class={cls} conf={conf:.2f}")

    if err:
        return _empty_response("غير معروف", 0.0,
            "⚠️ الموديل مش محمّل. حمّل egyptian_food_best.pt من Colab وحطه في models/exported/")

    if not cls or cls == "unknown" or conf < 0.10:
        return _empty_response("غير معروف", conf,
            f"مش قادر أحدد الأكلة ({int(conf*100)}%). جرب صورة أوضح.")

    # ── Active Learning Boost ─────────────────────────────────────────────────
    # If users corrected this class 5+ times → apply their correction
    try:
        boost = (await db.execute(text("""
            SELECT correct_class, COUNT(*) as cnt
            FROM needs_retraining
            WHERE predicted_class = :pred
            GROUP BY correct_class
            HAVING cnt >= 5
            ORDER BY cnt DESC
            LIMIT 1
        """), {"pred": cls})).fetchone()

        if boost:
            original_cls = cls
            cls = boost.correct_class
            # Get Arabic name: check CLASS_NAMES_AR first, fallback to value itself
            ar  = CLASS_NAMES_AR.get(cls, cls)
            logger.info(f"🧠 Active Learning boost: {original_cls} → {cls} ({boost.cnt} corrections)")
    except Exception as e:
        logger.debug(f"Boost check failed (non-critical): {e}")

    return await get_meal_from_class(cls, ar, conf, top3, db, user=user)