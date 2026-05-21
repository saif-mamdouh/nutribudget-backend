"""
fix_weights.py
══════════════
Updates unit_weight_g in fresh_products + ingredient_product_map
from the egypt_products_fixed.csv (which has real weights).

Run ONCE:
    cd D:\\desktop\\claude_GP
    python -m app.scripts.fix_weights
"""
import asyncio
import csv
import logging
from pathlib import Path
from sqlalchemy import text
from app.database import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# Path to the CSV — adjust if needed
CSV_PATH = Path("egypt_products_fixed.csv")


async def run():
    # Load CSV
    if not CSV_PATH.exists():
        log.error(f"CSV not found at {CSV_PATH.resolve()}")
        log.error("Copy egypt_products_fixed.csv to D:\\desktop\\claude_GP\\ first")
        return

    rows = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                sku   = r["sku"].strip()
                price = float(r["price"])
                wgt   = float(r["unit_weight_g"])
                if sku and price > 0 and wgt > 0:
                    rows.append((sku, price, wgt))
            except (ValueError, KeyError):
                continue

    log.info(f"Loaded {len(rows)} products from CSV")

    async with AsyncSessionLocal() as db:
        updated_fp = updated_ipm = 0

        # Batch update fresh_products in chunks of 500
        chunk_size = 500
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i+chunk_size]
            for sku, price, wgt in chunk:
                ppg = (price / wgt) * 100
                result = await db.execute(text("""
                    UPDATE fresh_products
                    SET unit_weight_g = :wgt,
                        price         = :price
                    WHERE sku = :sku
                      AND unit_weight_g != :wgt
                """), {"sku": sku, "price": price, "wgt": wgt})
                updated_fp += result.rowcount

            await db.commit()
            log.info(f"  fresh_products: updated {updated_fp} so far ({i+len(chunk)}/{len(rows)})...")

        # Now update ingredient_product_map from the corrected fresh_products
        result = await db.execute(text("""
            UPDATE ingredient_product_map ipm
            JOIN fresh_products fp ON fp.sku = ipm.sku
            SET ipm.unit_weight_g  = fp.unit_weight_g,
                ipm.price_per_100g = (ipm.price_egp / fp.unit_weight_g) * 100
            WHERE fp.unit_weight_g > 0
              AND fp.unit_weight_g != 1000
        """))
        updated_ipm = result.rowcount
        await db.commit()

        log.info(f"\n✅ Done!")
        log.info(f"   fresh_products updated:        {updated_fp}")
        log.info(f"   ingredient_product_map updated: {updated_ipm}")


if __name__ == "__main__":
    asyncio.run(run())
