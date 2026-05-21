"""
app/services/smart_ingredient_resolver.py
==========================================
Uses the Egyptian fine-tuned MiniLM model to find the best
product match for each recipe ingredient.

v2 Performance Fix:
  - Batch encode ALL ingredients at startup (not per-request)
  - Cache ingredient + product embeddings in memory
  - best_match_idx uses pre-computed vectors → no encode on hot path
"""

import logging
import numpy as np
from pathlib import Path
from typing import Optional

logger = logging.getLogger("nutribudget.resolver")

# Order: local first (fast for dev), HuggingFace second (for deployment),
# generic fallback last.
MODEL_PATHS = [
    "SaifMamdouh/egyptian-food-matcher",                       # HuggingFace (deployment) - try first
    Path("/app/models/egyptian_food_matcher"),                 # Docker container
    Path("models/egyptian_food_matcher"),                      # Local dev
    Path("D:/desktop/claude_GP/models/egyptian_food_matcher"), # Local dev (absolute)
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",  # Generic fallback
]


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
        self._ing_cache:  dict[str, np.ndarray] = {}  # ingredient_key → embedding
        self._prod_cache: dict[str, np.ndarray] = {}  # product_name   → embedding
        self._result_cache: dict[str, str]      = {}  # ingredient|products → best_name

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

    # ── Batch pre-warming (call once after loading all ingredient keys) ────────
    def warm_ingredients(self, ingredient_keys: list[str]) -> None:
        """
        Pre-encode all ingredient keys in one batch.
        Call this once at app startup / after product map loads.
        ~0.5s for 258 keys vs 2s+ for per-request encoding.
        """
        if self._model is None:
            return
        new_keys = [k for k in ingredient_keys if k not in self._ing_cache]
        if not new_keys:
            return
        try:
            embs = self._model.encode(
                new_keys, normalize_embeddings=True,
                batch_size=64, show_progress_bar=False
            )
            for k, emb in zip(new_keys, embs):
                self._ing_cache[k] = emb
            logger.info("🔥 Warmed %d ingredient embeddings", len(new_keys))
        except Exception as e:
            logger.warning("warm_ingredients failed: %s", e)

    def warm_products(self, product_names: list[str]) -> None:
        """Pre-encode product names in batch — called lazily per ingredient pool."""
        if self._model is None:
            return
        new_names = [n for n in product_names if n not in self._prod_cache]
        if not new_names:
            return
        try:
            embs = self._model.encode(
                new_names, normalize_embeddings=True,
                batch_size=64, show_progress_bar=False
            )
            for n, emb in zip(new_names, embs):
                self._prod_cache[n] = emb
        except Exception as e:
            logger.debug("warm_products failed: %s", e)

    # ── Core matching API ─────────────────────────────────────────────────────
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
            # Ingredient embedding — use cache or encode on demand
            if ingredient in self._ing_cache:
                ing_emb = self._ing_cache[ingredient]
            else:
                ing_emb = self._model.encode(
                    ingredient, normalize_embeddings=True
                )
                self._ing_cache[ingredient] = ing_emb

            # Product embeddings — batch-encode any missing names
            missing = [n for n in product_names if n not in self._prod_cache]
            if missing:
                self.warm_products(missing)

            prod_embs = np.array([
                self._prod_cache.get(n, self._model.encode(n, normalize_embeddings=True))
                for n in product_names
            ])

            # Cosine similarity → top-3 by similarity → cheapest among them
            scores   = np.dot(prod_embs, ing_emb)
            top_n    = min(3, len(candidates))
            top_idxs = np.argsort(scores)[::-1][:top_n]
            best_idx = int(min(
                top_idxs,
                key=lambda i: float(candidates[i].price_per_100g)
            ))

            self._result_cache[cache_key] = product_names[best_idx]
            return best_idx

        except Exception as e:
            logger.error("SmartResolver error for '%s': %s", ingredient, e)
            return 0

    def get_ingredient_emb(self, ingredient: str) -> Optional[np.ndarray]:
        """Return cached embedding for an ingredient key (used by meal_search)."""
        if not self._initialized:
            self.initialize()
        if ingredient in self._ing_cache:
            return self._ing_cache[ingredient]
        if self._model:
            emb = self._model.encode(ingredient, normalize_embeddings=True)
            self._ing_cache[ingredient] = emb
            return emb
        return None

    def get_batch_ingredient_embs(self, keys: list[str]) -> Optional[np.ndarray]:
        """
        Return matrix of embeddings for a list of ingredient keys.
        Used by meal_search for fast re-ranking without re-encoding.
        """
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
        logger.info("SmartResolver caches cleared")

    @property
    def model_source(self) -> str:
        return self._source or "none"

    @property
    def is_fine_tuned(self) -> bool:
        return bool(self._source and "egyptian-food-matcher" in str(self._source).replace("_", "-"))


# ── Global singleton ──────────────────────────────────────────────────────────
resolver = SmartIngredientResolver()
