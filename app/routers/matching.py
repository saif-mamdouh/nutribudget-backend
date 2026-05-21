from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.mapping import ProductNutritionMap
from app.models.product import Product
from app.models.nutrition import NutritionFact
from app.schemas.product import MappingResponse, NutritionCreate, NutritionResponse
from app.services.auth import get_current_user
from app.services import matching as match_service
from app.models.user import User

router = APIRouter(prefix="/match", tags=["Matching Engine"])


# ── POST /match/run — trigger the full matching pipeline ──────────────────────
class RunMatchRequest(BaseModel):
    product_ids: Optional[list[int]] = None   # None = all unmatched
    force_rematch: bool = False


@router.post("/run")
async def run_matching(
    payload: RunMatchRequest = Body(default=RunMatchRequest()),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Trigger the Fuzzy + Embedding matching pipeline.
    Returns a summary: matched, unmatched, high/low confidence counts.
    """
    result = await match_service.run_matching(
        db,
        product_ids=payload.product_ids,
        force_rematch=payload.force_rematch,
    )
    return result


# ── GET /match/preview — preview matches for a name without saving ────────────
@router.get("/preview")
async def preview_match(
    name: str = Query(..., description="Product name to test the matching engine"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Preview fuzzy + embedding candidates for a given product name.
    Nothing is saved — useful for tuning and debugging.
    """
    return await match_service.preview_match(name, db)


# ── GET /match/stats — mapping coverage stats ─────────────────────────────────
@router.get("/stats")
async def match_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Summary of matching coverage across all products."""
    total_products  = (await db.execute(select(func.count()).select_from(Product))).scalar()
    total_mappings  = (await db.execute(select(func.count()).select_from(ProductNutritionMap))).scalar()
    high_conf       = (await db.execute(
        select(func.count()).select_from(ProductNutritionMap)
        .where(ProductNutritionMap.confidence_score >= 0.75)
    )).scalar()
    low_conf        = (await db.execute(
        select(func.count()).select_from(ProductNutritionMap)
        .where(ProductNutritionMap.confidence_score < 0.75)
    )).scalar()

    return {
        "total_products":    total_products,
        "total_mapped":      total_mappings,
        "unmapped":          total_products - total_mappings,
        "high_confidence":   high_conf,   # >= 0.75 → enters optimizer
        "low_confidence":    low_conf,    # < 0.75  → needs review
        "coverage_pct":      round(total_mappings / total_products * 100, 1) if total_products else 0,
    }


# ── GET /match/low-confidence — review flagged mappings ───────────────────────
@router.get("/low-confidence")
async def low_confidence_mappings(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    List mappings with confidence < 0.75 — these need manual review
    before the optimizer can use them.
    """
    result = await db.execute(
        select(ProductNutritionMap)
        .where(ProductNutritionMap.confidence_score < 0.75)
        .order_by(ProductNutritionMap.confidence_score.asc())
        .limit(limit)
    )
    mappings = result.scalars().all()
    return [
        {
            "mapping_id":    m.id,
            "product_id":    m.product_id,
            "nutrition_id":  m.nutrition_id,
            "confidence":    m.confidence_score,
            "method":        m.match_method,
        }
        for m in mappings
    ]


# ── PATCH /match/{mapping_id}/approve — manually approve a low-conf mapping ──
@router.patch("/{mapping_id}/approve", response_model=dict)
async def approve_mapping(
    mapping_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Manually approve a low-confidence mapping by setting confidence = 1.0
    and method = 'manual'. This allows it to enter the optimizer.
    """
    result = await db.execute(
        select(ProductNutritionMap).where(ProductNutritionMap.id == mapping_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    mapping.confidence_score = 1.0
    mapping.match_method = "manual"
    db.add(mapping)
    return {"mapping_id": mapping_id, "confidence": 1.0, "method": "manual"}


# ── POST /match/nutrition — add or update nutrition facts ─────────────────────
@router.post("/nutrition", response_model=NutritionResponse, status_code=201)
async def add_nutrition(
    payload: NutritionCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Upsert a nutrition fact entry (INSERT … ON DUPLICATE KEY UPDATE).
    Safe to call multiple times with the same normalized_name.
    After adding entries, run POST /match/run to update mappings.
    """
    from app.models.nutrition import NutritionFact as NF

    upsert_sql = text("""
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
    await db.execute(upsert_sql, payload.model_dump())
    await db.flush()

    # Fetch the final row to return
    result = await db.execute(
        select(NF).where(NF.normalized_name == payload.normalized_name)
    )
    return result.scalar_one()


# ── GET /match/nutrition — list nutrition catalogue ───────────────────────────
@router.get("/nutrition", response_model=list[NutritionResponse])
async def list_nutrition(
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from app.models.nutrition import NutritionFact as NF
    stmt = select(NF)
    if q:
        stmt = stmt.where(NF.normalized_name.ilike(f"%{q}%"))
    result = await db.execute(stmt.limit(limit))
    return result.scalars().all()
