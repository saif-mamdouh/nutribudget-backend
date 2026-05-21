"""
routers/admin.py
─────────────────
Admin-only endpoints for bulk dataset uploads.
All routes require is_admin = True.
"""

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth import get_current_user
from app.models.user import User
from app.services.bulk_upload import (
    upload_products_csv,
    upload_nutrition_csv,
    upload_mapping_csv,
    upload_recipes_csv,
)

router = APIRouter(prefix="/admin", tags=["Admin"])

MAX_SIZE = 50 * 1024 * 1024   # 50 MB


# ── Admin guard dependency ────────────────────────────────────────────────────
async def get_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# ── POST /admin/upload/products ───────────────────────────────────────────────
@router.post("/upload/products")
async def bulk_upload_products(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin),
):
    """
    Upload egypt_products_final.csv
    Columns: source, sku, category, product_name, price, unit_weight_g
    """
    raw = await file.read()
    if len(raw) > MAX_SIZE:
        raise HTTPException(413, "File too large (max 50MB)")
    result = await upload_products_csv(raw, db)
    return {"status": "ok", "dataset": "products", **result}


# ── POST /admin/upload/nutrition ──────────────────────────────────────────────
@router.post("/upload/nutrition")
async def bulk_upload_nutrition(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin),
):
    """
    Upload nutrition_facts_clean.csv
    Columns: normalized_name, display_name, calories_per_100g,
             protein_g, carbs_g, fats_g, fiber_g, data_source
    """
    raw = await file.read()
    if len(raw) > MAX_SIZE:
        raise HTTPException(413, "File too large")
    result = await upload_nutrition_csv(raw, db)
    return {"status": "ok", "dataset": "nutrition", **result}


# ── POST /admin/upload/mapping ────────────────────────────────────────────────
@router.post("/upload/mapping")
async def bulk_upload_mapping(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin),
):
    """
    Upload ingredient_product_mapping.csv
    Columns: ingredient_key, sku, source, product_name,
             price_egp, unit_weight_g, price_per_100g
    """
    raw = await file.read()
    if len(raw) > MAX_SIZE:
        raise HTTPException(413, "File too large")
    result = await upload_mapping_csv(raw, db)
    return {"status": "ok", "dataset": "mapping", **result}


# ── POST /admin/upload/recipes ────────────────────────────────────────────────
@router.post("/upload/recipes")
async def bulk_upload_recipes(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin),
):
    """
    Upload egyptian_meals_dataset.csv
    Columns: recipe_id, recipe_name, meal_type,
             ingredients_json, instructions, prep_time
    """
    raw = await file.read()
    if len(raw) > MAX_SIZE:
        raise HTTPException(413, "File too large")
    result = await upload_recipes_csv(raw, db)
    return {"status": "ok", "dataset": "recipes", **result}


# ── GET /admin/stats ──────────────────────────────────────────────────────────
@router.get("/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin),
):
    """Overview of all dataset row counts."""
    from sqlalchemy import text
    tables = ["fresh_products", "nutrition_facts",
              "ingredient_product_map", "recipes"]
    result = {}
    for t in tables:
        r = await db.execute(text(f"SELECT COUNT(*) FROM {t}"))
        result[t] = r.scalar()
    return result
