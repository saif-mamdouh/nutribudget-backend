from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.product import Product
from app.schemas.product import ProductResponse, UploadSummary
from app.services.auth import get_current_user, get_current_admin
from app.services.product import process_csv_upload
from app.models.user import User

router = APIRouter(prefix="/products", tags=["Products"])

# Allowed MIME types for upload
_CSV_TYPES = {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"}
MAX_FILE_SIZE = 20 * 1024 * 1024   # 20 MB


# ── POST /upload-csv (ADMIN ONLY) ─────────────────────────────────────────────
@router.post("/upload-csv", response_model=UploadSummary, status_code=200)
async def upload_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),   # ✅ CHANGED HERE
):
    """
    Upload a CSV file with columns: source, sku, category, product_name, price.
    Performs deduplication, name normalisation, and batch upsert.
    Max file size: 20 MB.
    """
    content_type = (file.content_type or "").lower()
    if content_type not in _CSV_TYPES and not (file.filename or "").endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only CSV files are accepted.",
        )

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 20 MB limit.",
        )

    result = await process_csv_upload(raw, db)

    # Invalidate caches after CSV upload
    try:
        from app.services.meal_optimizer import invalidate_priced_recipes_cache
        invalidate_priced_recipes_cache()
    except Exception:
        pass

    return result


# ── GET /products ─────────────────────────────────────────────────────────────
@router.get("", response_model=dict)
async def list_products(
    category:  Optional[str]   = Query(None),
    source:    Optional[str]   = Query(None),
    q:         Optional[str]   = Query(None, description="Search by product name"),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    limit:  int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """List products with optional filters. Returns {items, total} for pagination."""
    # Base filter
    filters = []
    if category:  filters.append(Product.category.ilike(f"%{category}%"))
    if source:    filters.append(Product.source == source)
    if q:
        filters.append(or_(
            Product.product_name.ilike(f"%{q}%"),
            Product.normalized_name.ilike(f"%{q}%"),
        ))
    if min_price is not None: filters.append(Product.price >= min_price)
    if max_price is not None: filters.append(Product.price <= max_price)

    # Count total
    count_stmt = select(func.count()).select_from(Product)
    if filters:
        from sqlalchemy import and_
        count_stmt = count_stmt.where(and_(*filters))
    total = (await db.execute(count_stmt)).scalar()

    # Fetch page
    stmt = select(Product)
    if filters:
        from sqlalchemy import and_
        stmt = stmt.where(and_(*filters))
    stmt = stmt.order_by(Product.last_updated.desc()).offset(offset).limit(limit)
    items = (await db.execute(stmt)).scalars().all()

    from app.schemas.product import ProductResponse as PR
    return {
        "items": [PR.model_validate(p) for p in items],
        "total": total,
    }


# ── GET /products/stats ───────────────────────────────────────────────────────
@router.get("/stats", response_model=dict)
async def product_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Quick summary: total products, sources, categories."""
    total   = (await db.execute(select(func.count()).select_from(Product))).scalar()
    sources = (await db.execute(select(Product.source).distinct())).scalars().all()
    cats    = (await db.execute(select(Product.category).distinct())).scalars().all()
    return {
        "total_products": total,
        "sources": sources,
        "categories": [c for c in cats if c],
    }


# ── GET /products/{id} ────────────────────────────────────────────────────────
@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return product

# ── PATCH /products/{id} (ADMIN ONLY) ────────────────────────────────────────
from pydantic import BaseModel

class ProductUpdate(BaseModel):
    product_name:  Optional[str]   = None
    category:      Optional[str]   = None
    price:         Optional[float] = None
    unit_weight_g: Optional[int]   = None

@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    payload:    ProductUpdate,
    db:         AsyncSession = Depends(get_db),
    _:          User         = Depends(get_current_admin),
):
    """Update product fields (admin only)."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    db.add(product)
    await db.flush()
    await db.refresh(product)

    # Invalidate caches so changes are reflected immediately
    try:
        from app.services.meal_optimizer import invalidate_priced_recipes_cache
        invalidate_priced_recipes_cache()
    except Exception:
        pass

    return product
