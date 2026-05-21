"""
services/product.py
───────────────────
Handles all data pipeline operations:
  • CSV parsing + validation
  • In-memory deduplication (seen_skus set)
  • Batch upsert into fresh_products (INSERT … ON DUPLICATE KEY UPDATE)
  • Normalised name population
"""

import csv
import io
import logging
from typing import IO

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.product import UploadSummary
from app.utils.normalizer import normalize_name

logger = logging.getLogger("nutribudget.pipeline")

# Expected CSV columns (case-insensitive, strips whitespace)
REQUIRED_COLS = {"source", "sku", "product_name", "price"}
OPTIONAL_COLS = {"category"}

BATCH_SIZE = 500     # rows per INSERT batch — balances RAM vs round-trips


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _parse_price(val: str) -> float:
    """Strips currency symbols and parses to float. Returns 0.0 on failure."""
    import re
    cleaned = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _clean_name(val: str) -> str:
    import re
    val = val.replace("\n", " ").replace("\r", "")
    return re.sub(r"\s+", " ", val).strip()


def _parse_csv(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    """
    Parses raw CSV bytes.
    Returns (valid_rows, errors).
    Each valid row is a dict with keys: source, sku, category, product_name, price, normalized_name.
    """
    errors: list[str] = []
    rows: list[dict] = []
    seen: set[str] = set()

    try:
        text_io = io.StringIO(file_bytes.decode("utf-8-sig"))  # utf-8-sig handles BOM from Excel
        reader = csv.DictReader(text_io)
    except UnicodeDecodeError:
        # Fallback to cp1256 (common in Egyptian Excel exports)
        text_io = io.StringIO(file_bytes.decode("cp1256", errors="replace"))
        reader = csv.DictReader(text_io)

    if reader.fieldnames is None:
        return [], ["CSV file appears empty or has no header row."]

    # Normalise column headers
    col_map = {c.strip().lower(): c for c in reader.fieldnames}
    missing = REQUIRED_COLS - set(col_map.keys())
    if missing:
        return [], [f"Missing required columns: {', '.join(sorted(missing))}"]

    for line_num, raw_row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items()}

        source       = row.get("source", "")
        sku          = row.get("sku", "")
        category     = row.get("category", "")
        product_name = _clean_name(row.get("product_name", ""))
        price        = _parse_price(row.get("price", "0"))

        # Validation
        if not sku:
            errors.append(f"Line {line_num}: missing SKU — skipped")
            continue
        if not product_name:
            errors.append(f"Line {line_num}: missing product_name — skipped")
            continue
        if price <= 0:
            errors.append(f"Line {line_num}: SKU={sku} has price=0 — skipped")
            continue

        dedup_key = f"{source}_{sku}"
        if dedup_key in seen:
            errors.append(f"Line {line_num}: duplicate SKU={sku} in file — skipped")
            continue
        seen.add(dedup_key)

        rows.append({
            "source":          source,
            "sku":             sku,
            "category":        category,
            "product_name":    product_name,
            "normalized_name": normalize_name(product_name),
            "price":           price,
        })

    return rows, errors


# ── Database upsert ───────────────────────────────────────────────────────────

async def upsert_products(db: AsyncSession, rows: list[dict]) -> dict:
    """
    Batch upserts rows using MySQL's INSERT … ON DUPLICATE KEY UPDATE.
    Returns a dict with inserted/updated counts.
    """
    inserted = updated = 0

    upsert_sql = text("""
        INSERT INTO fresh_products
            (source, sku, category, product_name, normalized_name, price)
        VALUES
            (:source, :sku, :category, :product_name, :normalized_name, :price)
        ON DUPLICATE KEY UPDATE
            category        = VALUES(category),
            product_name    = VALUES(product_name),
            normalized_name = VALUES(normalized_name),
            price           = VALUES(price),
            last_updated    = CURRENT_TIMESTAMP
    """)

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        result = await db.execute(upsert_sql, batch)
        # MySQL: rowcount=1 → insert, rowcount=2 → update on duplicate
        inserted += sum(1 for _ in batch if result.rowcount == 1)
        updated  += sum(1 for _ in batch if result.rowcount == 2)
        await db.commit()
        logger.info(f"💾 Batch {i // BATCH_SIZE + 1}: {len(batch)} rows upserted.")

    return {"inserted": inserted, "updated": updated}


# ── Main pipeline entry ───────────────────────────────────────────────────────

async def process_csv_upload(file_bytes: bytes, db: AsyncSession) -> UploadSummary:
    rows, parse_errors = _parse_csv(file_bytes)
    skipped = len(parse_errors)

    if not rows:
        return UploadSummary(
            total_rows=0, inserted=0, updated=0,
            skipped=skipped, errors=len(parse_errors),
            message="No valid rows found. Check errors.",
        )

    try:
        counts = await upsert_products(db, rows)
    except Exception as e:
        logger.error(f"DB upsert failed: {e}")
        return UploadSummary(
            total_rows=len(rows), inserted=0, updated=0,
            skipped=skipped, errors=1,
            message=f"Database error: {str(e)}",
        )

    return UploadSummary(
        total_rows=len(rows) + skipped,
        inserted=counts["inserted"],
        updated=counts["updated"],
        skipped=skipped,
        errors=0,
        message=f"✅ Pipeline complete. {counts['inserted']} new, {counts['updated']} updated.",
    )
