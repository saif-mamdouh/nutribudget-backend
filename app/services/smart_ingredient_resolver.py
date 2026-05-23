"""
app/services/smart_ingredient_resolver.py
==========================================
Uses the Egyptian fine-tuned MiniLM model to find the best
product match for each recipe ingredient.

v4 — Precomputed Embeddings Cache:
  - Loads product_embeddings.npz at startup (instant, no encoding)
  - Falls back to on-demand encoding if file not found
  - No more 6-hour warming loop!
"""

import logging
import numpy as np
from pathlib import Path
from typing import Optional

logger = logging.getLogger("nutribudget.resolver")

MODEL_PATHS = [
    "SaifMamdouh/egyptian-food-matcher",
    Path("/app/models/egyptian_food_matcher"),
    Path("models/egyptian_food_matcher"),
    Path("D:/desktop/claude_GP/models/egyptian_food_matcher"),
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
]

# Path to precomputed embeddings file
EMBEDDINGS_FILE_PATHS = [
    Path("/app/data/product_embeddings.npz"),       # Railway/Docker
    Path("data/product_embeddings.npz"),             # Local dev
    Path("D:/desktop/claude_GP/data/product_embeddings.npz"),  # Local absolute
]

_RESULT_CACHE_MAX = 1000


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
        self._products_warmed: bool               = False

        # ── Load model ────────────────────────────────────────────────────────
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

        # ── Load precomputed product embeddings ───────────────────────────────
        self._load_precomputed_embeddings()

        self._initialized = True

    def _load_precomputed_embeddings(self):
        """Load precomputed product embeddings from .npz file if available."""
        for emb_path in EMBEDDINGS_FILE_PATHS:
            if not emb_path.exists():
                continue
            try:
                data = np.load(emb_path, allow_pickle=True)
                names      = list(data['product_names'])
                embeddings = data['embeddings']

                for name, emb in zip(names, embeddings):
                    self._prod_cache[str(name)] = emb

                self._products_warmed = True
                logger.info(
                    f"✅ Loaded precomputed embeddings: {len(self._prod_cache)} products "
                    f"from {emb_path} — no warming needed!"
                )
                return
            except Exception as e:
                logger.warning(f"Failed to load precomputed embeddings from {emb_path}: {e}")

        logger.info(
            "ℹ️  No precomputed embeddings file found — "
            "will encode on-demand. Run scripts/precompute_product_embeddings.py to fix."
        )

    def warm_ingredients(self, ingredient_keys: list[str]) -> None:
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
        """Encode missing product names on-demand (only if not precomputed)."""
        if self._model is None:
            return

        # If precomputed file was loaded → only encode truly missing products
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

            # Mark as warmed after encoding a reasonable batch
            if len(self._prod_cache) >= 50:
                self._products_warmed = True

        except Exception as e:
            logger.debug("warm_products failed: %s", e)

    def best_match_idx(self, ingredient: str, candidates: list, product_names: list) -> int:
        if not self._initialized:
            self.initialize()
        if self._model is None or not product_names:
            return 0

        # Result cache (fastest path)
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

            # Product embeddings
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

            # Cache result
            if len(self._result_cache) >= _RESULT_CACHE_MAX:
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
        self._ing_cache.clear()
        self._prod_cache.clear()
        self._result_cache.clear()
        self._products_warmed = False
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