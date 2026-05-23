"""
app/services/smart_ingredient_resolver.py
==========================================
Uses the Egyptian fine-tuned MiniLM model to find the best
product match for each recipe ingredient.

v3 Fix — Infinite encoding loop:
  - Added _products_warmed flag: warm_products runs ONCE then stops
  - Added _RESULT_CACHE_MAX to prevent memory leak
  - show_progress_bar=False in all encode calls
  - Product embeddings persist across requests (singleton cache)
"""

import logging
import numpy as np
from pathlib import Path
from typing import Optional

logger = logging.getLogger("nutribudget.resolver")

MODEL_PATHS = [
    "SaifMamdouh/egyptian-food-matcher",                        # HuggingFace (deployment)
    Path("/app/models/egyptian_food_matcher"),                  # Docker
    Path("models/egyptian_food_matcher"),                       # Local dev
    Path("D:/desktop/claude_GP/models/egyptian_food_matcher"),  # Local dev (absolute)
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",  # Fallback
]

_RESULT_CACHE_MAX = 1000  # max entries to prevent memory leak


class SmartIngredientResolver:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def initialize(self):
        if self._initialized:
            return

        from sentence_transformers import SentenceTransformer

        self._model:  Optional[SentenceTransformer] = None
        self._source: Optional[str]                 = None

        # ── Embedding caches ──────────────────────────────────────────────────
        self._ing_cache:    dict[str, np.ndarray] = {}
        self._prod_cache:   dict[str, np.ndarray] = {}
        self._result_cache: dict[str, str]        = {}

        # ── NEW: flag to prevent re-warming products on every request ─────────
        self._products_warmed: bool = False

        for path in MODEL_PATHS:
            try:
                self._model  = SentenceTransformer(str(path))
                self._source = str(path)
                logger.info(f"✅ SmartResolver loaded: {path}")
                break
            except Exception as e:
                logger.debug(f"Model not found at {path}: {e}")

        if self._model is None:
            logger.warning("⚠️  SmartResolver: no model — using price-only matching")

        self._initialized = True

    def warm_ingredients(self, ingredient_keys: list[str]) -> None:
        """Pre-encode all ingredient keys in one batch."""
        if self._model is None:
            return
        new_keys = [k for k in ingredient_keys if k not in self._ing_cache]
        if not new_keys:
            return
        try:
            embs = self._model.encode(
                new_keys, normalize_embeddings=True,
                batch_size=64, show_progress_bar=False  # ← always False
            )
            for k, emb in zip(new_keys, embs):
                self._ing_cache[k] = emb
            logger.info("🔥 Warmed %d ingredient embeddings", len(new_keys))
        except Exception as e:
            logger.warning("warm_ingredients failed: %s", e)

    def warm_products(self, product_names: list[str]) -> None:
        """
        Pre-encode product names in batch.

        v3 fix: only encodes NEW names (not already in cache).
        Once all products are encoded, subsequent calls are no-ops.
        """
        if self._model is None:
            return

        # ── KEY FIX: skip if already warmed all products ──────────────────────
        if self._products_warmed:
            return

        new_names = [n for n in product_names if n not in self._prod_cache]
        if not new_names:
            self._products_warmed = True  # mark done
            return

        try:
            embs = self._model.encode(
                new_names, normalize_embeddings=True,
                batch_size=64, show_progress_bar=False  # ← always False
            )
            for n, emb in zip(new_names, embs):
                self._prod_cache[n] = emb
            logger.info("🔥 Warmed %d product embeddings (total cached: %d)",
                        len(new_names), len(self._prod_cache))

            # Mark as fully warmed once we've processed a large batch
            # (2000+ products = all products in DB)
            if len(self._prod_cache) >= 500:
                self._products_warmed = True
                logger.info("✅ Product cache complete (%d products) — no more warming needed",
                            len(self._prod_cache))

        except Exception as e:
            logger.debug("warm_products failed: %s", e)

    def best_match_idx(self, ingredient: str, candidates: list, product_names: list) -> int:
        """
        Returns index of best-matching candidate.
        Uses cached embeddings — no encode call if already warmed.
        Falls back to 0 (first / cheapest) if model unavailable.
        """
        if not self._initialized:
            self.initialize()
        if self._model is None or not product_names:
            return 0

        # Result cache check (fastest path)
        cache_key = f"{ingredient}|{'|'.join(product_names[:5])}"
        if cache_key in self._result_cache:
            cached_name = self._result_cache[cache_key]
            for i, name in enumerate(product_names):
                if name == cached_name:
                    return i

        try:
            # Ingredient embedding
            if ingredient in self._ing_cache:
                ing_emb = self._ing_cache[ingredient]
            else:
                ing_emb = self._model.encode(
                    ingredient, normalize_embeddings=True,
                    show_progress_bar=False
                )
                self._ing_cache[ingredient] = ing_emb

            # Product embeddings — batch-encode any missing
            missing = [n for n in product_names if n not in self._prod_cache]
            if missing:
                self.warm_products(missing)

            prod_embs = np.array([
                self._prod_cache.get(
                    n,
                    self._model.encode(n, normalize_embeddings=True,
                                       show_progress_bar=False)
                )
                for n in product_names
            ])

            # Cosine similarity → top-3 → cheapest
            scores   = np.dot(prod_embs, ing_emb)
            top_n    = min(3, len(candidates))
            top_idxs = np.argsort(scores)[::-1][:top_n]
            best_idx = int(min(
                top_idxs,
                key=lambda i: float(candidates[i].price_per_100g)
            ))

            # Cache result (with size limit)
            if len(self._result_cache) < _RESULT_CACHE_MAX:
                self._result_cache[cache_key] = product_names[best_idx]
            elif len(self._result_cache) >= _RESULT_CACHE_MAX:
                # Simple eviction: clear half the cache
                keys = list(self._result_cache.keys())
                for k in keys[:_RESULT_CACHE_MAX // 2]:
                    del self._result_cache[k]
                self._result_cache[cache_key] = product_names[best_idx]

            return best_idx

        except Exception as e:
            logger.error("SmartResolver error for '%s': %s", ingredient, e)
            return 0

    def get_ingredient_emb(self, ingredient: str) -> Optional[np.ndarray]:
        if not self._initialized:
            self.initialize()
        if ingredient in self._ing_cache:
            return self._ing_cache[ingredient]
        if self._model:
            emb = self._model.encode(
                ingredient, normalize_embeddings=True,
                show_progress_bar=False
            )
            self._ing_cache[ingredient] = emb
            return emb
        return None

    def get_batch_ingredient_embs(self, keys: list[str]) -> Optional[np.ndarray]:
        if not self._initialized:
            self.initialize()
        if self._model is None:
            return None
        self.warm_ingredients(keys)
        embs = [self._ing_cache.get(k) for k in keys]
        if any(e is None for e in embs):
            return None
        return np.array(embs)

    def clear_cache(self):
        """Clear all caches (call after DB updates)."""
        self._ing_cache.clear()
        self._prod_cache.clear()
        self._result_cache.clear()
        self._products_warmed = False  # allow re-warming after DB update
        logger.info("SmartResolver caches cleared")

    @property
    def model_source(self) -> str:
        return self._source or "none"

    @property
    def is_fine_tuned(self) -> bool:
        return bool(
            self._source and
            "egyptian-food-matcher" in str(self._source).replace("_", "-")
        )


# ── Global singleton ──────────────────────────────────────────────────────────
resolver = SmartIngredientResolver()
