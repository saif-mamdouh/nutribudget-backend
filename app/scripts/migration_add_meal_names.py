"""
migration_add_meal_names.py
═══════════════════════════
ONE-TIME migration: adds `meal_names` JSON column to `meal_plans`.

Stores the list of recipe names inside each plan so the History page
can show "ملوخية + كشري + فراخ مشوية" instead of just "Daily Plan #7".

Run ONCE before restarting the backend:
    cd D:\\desktop\\claude_GP
    python -m app.scripts.migration_add_meal_names
"""
import asyncio, logging
from sqlalchemy import text
from app.database import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

async def run():
    async with AsyncSessionLocal() as db:
        # 1. Add column if not exists
        try:
            await db.execute(text(
                "ALTER TABLE meal_plans ADD COLUMN meal_names TEXT NULL"
            ))
            await db.commit()
            log.info("✅ Column 'meal_names' added to meal_plans.")
        except Exception as e:
            if "Duplicate column" in str(e) or "1060" in str(e):
                log.info("ℹ  Column 'meal_names' already exists — skipping.")
            else:
                raise

        # 2. Back-fill existing "added" (single meal) rows from the message pattern
        # The add-meal endpoint saved: "'{recipe_name}' added to your plan history"
        # We can't recover the names of old MILP plans, but single meals we can try.
        log.info("ℹ  Old plans will show no meal names (expected). New ones will.")

if __name__ == "__main__":
    asyncio.run(run())
