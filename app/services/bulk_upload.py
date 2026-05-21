"""
services/bulk_upload.py
────────────────────────
Handles bulk CSV uploads for:
  1. Products CSV        (with unit_weight_g)
  2. Nutrition Facts CSV (267 rows → nutrition_facts table)
  3. Ingredient Mapping  (5640 rows → ingredient_product_map table)
  4. Recipes / Meals     (300 rows → recipes table)

All use INSERT … ON DUPLICATE KEY UPDATE (MySQL upsert) for idempotency.
"""

import csv
import io
import json
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.normalizer import normalize_name

logger = logging.getLogger("nutribudget.bulk")

BATCH = 500


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_csv(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    try:
        text_io = io.StringIO(file_bytes.decode("utf-8-sig"))
    except UnicodeDecodeError:
        text_io = io.StringIO(file_bytes.decode("cp1256", errors="replace"))
    reader = csv.DictReader(text_io)
    rows   = [{k.strip().lower(): (v or "").strip() for k, v in r.items()} for r in reader]
    return rows, []


def _to_float(v, default=0.0) -> float:
    try:
        return float(v) if v else default
    except (ValueError, TypeError):
        return default


async def _batch_execute(db: AsyncSession, sql: text, rows: list[dict]):
    for i in range(0, len(rows), BATCH):
        batch = rows[i: i + BATCH]
        await db.execute(sql, batch)
        await db.commit()
        logger.info(f"  💾 batch {i // BATCH + 1}: {len(batch)} rows")


# ── 1. Products (with unit_weight_g) ─────────────────────────────────────────

async def upload_products_csv(file_bytes: bytes, db: AsyncSession) -> dict:
    """
    Expected columns: source, sku, category, product_name, price, unit_weight_g
    """
    rows, _ = _read_csv(file_bytes)

    clean = []
    skipped = 0
    for r in rows:
        sku   = r.get("sku", "").strip()
        src   = r.get("source", "").strip()
        name  = r.get("product_name", "").strip()
        price = _to_float(r.get("price", "0"))
        wt    = _to_float(r.get("unit_weight_g", "1000"), 1000)

        if not sku or not name or price <= 0:
            skipped += 1
            continue

        clean.append({
            "source":          src,
            "sku":             sku,
            "category":        r.get("category", ""),
            "product_name":    name,
            "normalized_name": normalize_name(name),
            "price":           price,
            "unit_weight_g":   wt if wt > 0 else 1000,
        })

    sql = text("""
        INSERT INTO fresh_products
            (source, sku, category, product_name, normalized_name, price, unit_weight_g)
        VALUES
            (:source, :sku, :category, :product_name, :normalized_name, :price, :unit_weight_g)
        ON DUPLICATE KEY UPDATE
            category        = VALUES(category),
            product_name    = VALUES(product_name),
            normalized_name = VALUES(normalized_name),
            price           = VALUES(price),
            unit_weight_g   = VALUES(unit_weight_g),
            last_updated    = CURRENT_TIMESTAMP
    """)

    await _batch_execute(db, sql, clean)
    logger.info(f"✅ Products: {len(clean)} upserted, {skipped} skipped")
    return {"inserted": len(clean), "skipped": skipped, "total": len(rows)}


# ── 2. Nutrition Facts CSV ────────────────────────────────────────────────────

async def upload_nutrition_csv(file_bytes: bytes, db: AsyncSession) -> dict:
    """
    Expected columns: normalized_name, display_name, category,
                      calories_per_100g, protein_g, carbs_g, fats_g,
                      fiber_g, data_source
    """
    rows, _ = _read_csv(file_bytes)

    clean = []
    skipped = 0
    for r in rows:
        key = r.get("normalized_name", "").strip()
        if not key:
            skipped += 1
            continue
        clean.append({
            "normalized_name":  key,
            "display_name":     r.get("display_name", key),
            "calories_per_100g":_to_float(r.get("calories_per_100g")),
            "protein_g":        _to_float(r.get("protein_g")),
            "carbs_g":          _to_float(r.get("carbs_g")),
            "fats_g":           _to_float(r.get("fats_g")),
            "fiber_g":          _to_float(r.get("fiber_g")),
            "data_source":      r.get("data_source", "manual"),
        })

    sql = text("""
        INSERT INTO nutrition_facts
            (normalized_name, display_name, calories_per_100g,
             protein_g, carbs_g, fats_g, fiber_g, data_source)
        VALUES
            (:normalized_name, :display_name, :calories_per_100g,
             :protein_g, :carbs_g, :fats_g, :fiber_g, :data_source)
        ON DUPLICATE KEY UPDATE
            display_name      = VALUES(display_name),
            calories_per_100g = VALUES(calories_per_100g),
            protein_g         = VALUES(protein_g),
            carbs_g           = VALUES(carbs_g),
            fats_g            = VALUES(fats_g),
            fiber_g           = VALUES(fiber_g),
            data_source       = VALUES(data_source)
    """)

    await _batch_execute(db, sql, clean)
    logger.info(f"✅ Nutrition: {len(clean)} upserted, {skipped} skipped")
    return {"inserted": len(clean), "skipped": skipped, "total": len(rows)}


# ── 3. Ingredient → Product Mapping CSV ──────────────────────────────────────

async def upload_mapping_csv(file_bytes: bytes, db: AsyncSession) -> dict:
    """
    Expected columns: ingredient_key, sku, source, product_name,
                      price_egp, unit_weight_g, price_per_100g
    """
    rows, _ = _read_csv(file_bytes)

    clean = []
    skipped = 0
    for r in rows:
        key = r.get("ingredient_key", "").strip()
        sku = r.get("sku", "").strip()
        if not key or not sku:
            skipped += 1
            continue

        price_egp    = _to_float(r.get("price_egp"))
        unit_weight  = _to_float(r.get("unit_weight_g"), 1000)
        price_per100 = _to_float(r.get("price_per_100g"))

        # Recompute if missing
        if price_per100 == 0 and price_egp > 0 and unit_weight > 0:
            price_per100 = round(price_egp / unit_weight * 100, 4)

        clean.append({
            "ingredient_key": key,
            "sku":            sku,
            "source":         r.get("source", ""),
            "product_name":   r.get("product_name", ""),
            "price_egp":      price_egp,
            "unit_weight_g":  unit_weight,
            "price_per_100g": price_per100,
        })

    sql = text("""
        INSERT INTO ingredient_product_map
            (ingredient_key, sku, source, product_name,
             price_egp, unit_weight_g, price_per_100g)
        VALUES
            (:ingredient_key, :sku, :source, :product_name,
             :price_egp, :unit_weight_g, :price_per_100g)
        ON DUPLICATE KEY UPDATE
            source         = VALUES(source),
            product_name   = VALUES(product_name),
            price_egp      = VALUES(price_egp),
            unit_weight_g  = VALUES(unit_weight_g),
            price_per_100g = VALUES(price_per_100g)
    """)

    await _batch_execute(db, sql, clean)
    logger.info(f"✅ Mapping: {len(clean)} upserted, {skipped} skipped")
    return {"inserted": len(clean), "skipped": skipped, "total": len(rows)}


# ── 4. Recipes / Meals CSV ────────────────────────────────────────────────────

async def upload_recipes_csv(file_bytes: bytes, db: AsyncSession) -> dict:
    """
    Expected columns: recipe_id, recipe_name, meal_type,
                      ingredients_json, instructions, prep_time
    """
    rows, _ = _read_csv(file_bytes)

    clean = []
    skipped = 0
    for r in rows:
        rid  = r.get("recipe_id", "").strip()
        name = r.get("recipe_name", "").strip()
        ings = r.get("ingredients_json", "").strip()
        if not rid or not name or not ings:
            skipped += 1
            continue
        # Validate JSON
        try:
            parsed = json.loads(ings)
            assert isinstance(parsed, list)
        except Exception:
            skipped += 1
            continue

        clean.append({
            "recipe_id":        int(rid),
            "recipe_name":      name,
            "meal_type":        r.get("meal_type", ""),
            "ingredients_json": ings,
            "instructions":     r.get("instructions", ""),
            "prep_time":        int(_to_float(r.get("prep_time", "0"))),
        })

    sql = text("""
        INSERT INTO recipes
            (recipe_id, recipe_name, meal_type,
             ingredients_json, instructions, prep_time)
        VALUES
            (:recipe_id, :recipe_name, :meal_type,
             :ingredients_json, :instructions, :prep_time)
        ON DUPLICATE KEY UPDATE
            recipe_name      = VALUES(recipe_name),
            meal_type        = VALUES(meal_type),
            ingredients_json = VALUES(ingredients_json),
            instructions     = VALUES(instructions),
            prep_time        = VALUES(prep_time)
    """)

    await _batch_execute(db, sql, clean)
    logger.info(f"✅ Recipes: {len(clean)} upserted, {skipped} skipped")
    return {"inserted": len(clean), "skipped": skipped, "total": len(rows)}
