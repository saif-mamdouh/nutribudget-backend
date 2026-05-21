"""
services/matching.py
────────────────────
Orchestrates the full matching pipeline:

  STAGE 1 — Fuzzy matching (rapidfuzz)
    Fast, zero-dependency, good for exact/near-exact name variants.
    Threshold: 72/100. Runs in milliseconds for 10k products.

  STAGE 2 — Embedding matching (sentence-transformers)
    Semantic similarity — catches cross-language and paraphrase matches
    that fuzzy fails on. Only runs for products that fuzzy couldn't match.
    Threshold: 0.72 cosine similarity.

  CONFIDENCE FUSION:
    fuzzy_only:     confidence = fuzzy_score (0–1)
    embedding_only: confidence = embedding_score × 0.95  (slight penalty)
    both agree:     confidence = max(fuzzy, embedding)   (strong signal)

  OUTPUT → product_nutrition_map table
    confidence >= 0.75 → used by optimizer
    confidence <  0.75 → stored but flagged (needs manual review)
"""

import logging
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.nutrition import NutritionFact
from app.models.mapping import ProductNutritionMap
from app.utils.fuzzy_matcher import find_best_fuzzy_match
from app.utils.embedding_matcher import EmbeddingMatcher
from app.utils.normalizer import normalize_name

# ── Brand/packaging keywords to strip before matching ────────────────────────
# These create noise for the matcher and reduce confidence scores
STRIP_KEYWORDS = {
    # Common Egyptian/regional brands
    "almarai", "tabarak", "thimar", "ezbetna", "obour", "sutas", "merai",
    "rich", "fresh", "farm", "zadna", "pico", "taste", "premium",
    "juhayna", "domty", "panda", "lamar", "danette", "activia",
    # Packaging descriptors
    "vacuum", "fresh", "natural", "extra", "light", "plain", "smoked",
    "pieces", "piece", "counts", "count", "pack", "bundle", "bundles",
    "spreadable", "luncheon", "treats", "ball", "long", "cubes",
    # Size markers
    "kilo", "kilogram", "kg", "gram", "gm", "g", "ml", "liter",
    "small", "large", "medium", "mini",
}

def _strip_brand_noise(name: str) -> str:
    """Removes brand and packaging tokens to improve matching."""
    import re
    tokens = name.lower().split()
    # Drop pure numbers and known brand/packaging words
    cleaned = [
        t for t in tokens
        if t not in STRIP_KEYWORDS
        and not re.fullmatch(r"\d+", t)        # pure digits
        and not re.fullmatch(r"\d+gm?", t)     # "250g", "250gm"
        and len(t) > 1                          # drop single-letter tokens
    ]
    return " ".join(cleaned) if cleaned else name

logger = logging.getLogger("nutribudget.matching")

FUZZY_THRESHOLD     = 60
EMBEDDING_THRESHOLD = 0.55
OPTIMIZER_THRESHOLD = 0.65   # minimum confidence to enter the optimizer


# ── Nutrition catalogue cache ─────────────────────────────────────────────────

async def _load_nutrition_catalogue(
    db: AsyncSession,
) -> dict[str, int]:
    """Returns {normalized_name: nutrition_fact_id}"""
    result = await db.execute(
        select(NutritionFact.id, NutritionFact.normalized_name)
    )
    return {row.normalized_name: row.id for row in result}


# ── Core match logic ──────────────────────────────────────────────────────────

def _match_one(
    product_name: str,
    catalogue: dict[str, int],
    embedding_matcher: EmbeddingMatcher,
) -> Optional[tuple[int, float, str]]:
    """
    Match a single normalised product name against the nutrition catalogue.

    Returns:
        (nutrition_id, confidence, method) or None
    """
    candidates = list(catalogue.keys())
    if not candidates:
        return None

    # STAGE 1 — Fuzzy
    fuzzy_result = find_best_fuzzy_match(product_name, candidates, FUZZY_THRESHOLD)

    # STAGE 2 — Embedding (always run to potentially boost confidence)
    embed_result = None
    if embedding_matcher.is_ready:
        embed_result = embedding_matcher.find_best(product_name, EMBEDDING_THRESHOLD)

    # ── Fusion ────────────────────────────────────────────────────────────────
    if fuzzy_result and embed_result:
        f_name, f_conf = fuzzy_result
        e_name, e_conf = embed_result

        if f_name == e_name:
            # Both agree — high confidence
            confidence = max(f_conf, e_conf)
            method = "fuzzy+embedding"
            best_name = f_name
        else:
            # Disagree — trust the higher score
            if f_conf >= e_conf:
                confidence, method, best_name = f_conf, "fuzzy", f_name
            else:
                confidence, method, best_name = e_conf * 0.95, "embedding", e_name

    elif fuzzy_result:
        best_name, confidence = fuzzy_result
        method = "fuzzy"

    elif embed_result:
        best_name, e_conf = embed_result
        confidence = e_conf * 0.95   # slight penalty for embedding-only
        method = "embedding"

    else:
        return None

    nutrition_id = catalogue.get(best_name)
    if nutrition_id is None:
        return None

    return nutrition_id, round(confidence, 4), method


# ── Batch matching ────────────────────────────────────────────────────────────

async def run_matching(
    db: AsyncSession,
    product_ids: Optional[list[int]] = None,
    force_rematch: bool = False,
) -> dict:
    """
    Run the full matching pipeline.

    Args:
        product_ids:   specific products to match (None = all unmatched)
        force_rematch: if True, deletes existing mappings and re-runs

    Returns:
        {matched, unmatched, high_confidence, low_confidence, total}
    """
    # 1. Load nutrition catalogue
    catalogue = await _load_nutrition_catalogue(db)
    if not catalogue:
        logger.warning("⚠️  Nutrition catalogue is empty — upload nutrition data first.")
        return {"matched": 0, "unmatched": 0, "error": "Empty nutrition catalogue"}

    catalogue_names = list(catalogue.keys())

    # 2. Pre-index embeddings (once per run)
    matcher = EmbeddingMatcher.instance()
    if catalogue_names:
        matcher.index(catalogue_names)

    # 3. Load products to match
    stmt = select(Product)
    if product_ids:
        stmt = stmt.where(Product.id.in_(product_ids))

    if not force_rematch and not product_ids:
        # Only unmatched products
        matched_ids_subq = select(ProductNutritionMap.product_id)
        stmt = stmt.where(Product.id.not_in(matched_ids_subq))

    result = await db.execute(stmt)
    products = result.scalars().all()

    if not products:
        logger.info("✅ No products to match.")
        return {"matched": 0, "unmatched": 0, "total": 0}

    logger.info(f"🔍 Matching {len(products)} products against {len(catalogue)} nutrition entries …")

    # 4. Optional: delete existing mappings for force_rematch
    if force_rematch and product_ids:
        await db.execute(
            delete(ProductNutritionMap).where(
                ProductNutritionMap.product_id.in_(product_ids)
            )
        )

    # 5. Match each product
    matched = unmatched = high_conf = low_conf = 0
    new_mappings: list[ProductNutritionMap] = []

    for product in products:
        raw_query = product.normalized_name or normalize_name(product.product_name)
        # Try stripped version first (better recall), fall back to raw
        stripped  = _strip_brand_noise(raw_query)
        match = _match_one(stripped, catalogue, matcher)
        if match is None and stripped != raw_query:
            # Fall back to raw query if stripped didn't match
            match = _match_one(raw_query, catalogue, matcher)

        if match is None:
            unmatched += 1
            logger.debug(f"  ✗ No match: '{product.product_name}'")
            continue

        nutrition_id, confidence, method = match
        new_mappings.append(
            ProductNutritionMap(
                product_id=product.id,
                nutrition_id=nutrition_id,
                confidence_score=confidence,
                match_method=method,
            )
        )
        matched += 1
        if confidence >= OPTIMIZER_THRESHOLD:
            high_conf += 1
        else:
            low_conf += 1

        logger.debug(
            f"  ✓ [{method:<18}] conf={confidence:.3f} | "
            f"'{product.product_name}' → nutrition_id={nutrition_id}"
        )

    # 6. Bulk upsert — ON DUPLICATE KEY UPDATE prevents duplicate errors
    # when force_rematch=True or when _seed_data is called multiple times in tests.
    if new_mappings:
        from sqlalchemy import text
        upsert_sql = text("""
            INSERT INTO product_nutrition_map
                (product_id, nutrition_id, confidence_score, match_method)
            VALUES
                (:product_id, :nutrition_id, :confidence_score, :match_method)
            ON DUPLICATE KEY UPDATE
                confidence_score = VALUES(confidence_score),
                match_method     = VALUES(match_method)
        """)
        await db.execute(upsert_sql, [
            {
                "product_id":       m.product_id,
                "nutrition_id":     m.nutrition_id,
                "confidence_score": m.confidence_score,
                "match_method":     m.match_method,
            }
            for m in new_mappings
        ])
        await db.flush()
        logger.info(f"💾 Saved {len(new_mappings)} mappings.")

    return {
        "total": len(products),
        "matched": matched,
        "unmatched": unmatched,
        "high_confidence": high_conf,    # confidence >= 0.75 → enters optimizer
        "low_confidence": low_conf,      # confidence < 0.75  → needs review
    }


# ── Single-product preview (for API) ─────────────────────────────────────────

async def preview_match(
    product_name: str,
    db: AsyncSession,
) -> dict:
    """
    Returns matching candidates for a given product name without saving.
    Used by the /match/preview endpoint.
    """
    catalogue = await _load_nutrition_catalogue(db)
    if not catalogue:
        return {"error": "Empty nutrition catalogue"}

    normalized = normalize_name(product_name)
    candidates = list(catalogue.keys())

    matcher = EmbeddingMatcher.instance()
    if not matcher.is_ready:
        matcher.index(candidates)

    # Fuzzy top-5
    from rapidfuzz import process, fuzz
    fuzzy_top = process.extract(
        normalized, candidates,
        scorer=fuzz.token_set_ratio,
        limit=5,
    )

    # Embedding top-5
    embed_top = matcher.find_top_k(normalized, k=5) if matcher.is_ready else []

    return {
        "query": product_name,
        "normalized": normalized,
        "fuzzy_candidates": [
            {"name": name, "score": round(score / 100, 4)}
            for name, score, _ in fuzzy_top
        ],
        "embedding_candidates": [
            {"name": name, "score": score}
            for name, score in embed_top
        ],
    }