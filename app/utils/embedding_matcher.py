"""
utils/embedding_matcher.py
──────────────────────────
Semantic similarity matching using sentence-transformers.

Model choice — paraphrase-multilingual-MiniLM-L12-v2:
  • 50+ languages including Arabic → handles mixed Arabic/English product names
  • 384-dim embeddings, ~120MB model size — lightweight for a GP project
  • Outperforms fuzzy matching for conceptually similar but lexically different names:
      "دجاج مشوي" ↔ "grilled chicken" → high cosine similarity
      "لحم بقري" ↔ "beef"             → high cosine similarity

Architecture:
  • Singleton EmbeddingMatcher — model loaded ONCE per process (heavy operation)
  • Embeddings for the nutrition catalogue are pre-computed and cached in RAM
  • Only product queries are encoded at match time (fast, ~2ms each)
"""

from __future__ import annotations
import logging
from typing import Optional
import numpy as np

logger = logging.getLogger("nutribudget.embedding")

# Lazy imports — only loaded when EmbeddingMatcher is first used
_sentence_transformers = None
_torch = None

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_THRESHOLD = 0.72   # cosine similarity cutoff (0–1)


def _load_libs():
    global _sentence_transformers, _torch
    if _sentence_transformers is None:
        try:
            from sentence_transformers import SentenceTransformer
            import torch
            _sentence_transformers = SentenceTransformer
            _torch = torch
            logger.info(f"✅ sentence-transformers loaded. Model: {MODEL_NAME}")
        except ImportError as e:
            logger.warning(f"⚠️  sentence-transformers not available: {e}. Embedding matching disabled.")
            _sentence_transformers = False   # mark as unavailable


class EmbeddingMatcher:
    """
    Singleton semantic matcher.
    Usage:
        matcher = EmbeddingMatcher.instance()
        matcher.index(nutrition_names)
        result = matcher.find_best(product_name)
    """

    _instance: Optional["EmbeddingMatcher"] = None

    def __init__(self):
        _load_libs()
        self._model = None
        self._index_names: list[str] = []
        self._index_vecs: Optional[np.ndarray] = None   # (N, 384)
        self._available = bool(_sentence_transformers)

    @classmethod
    def instance(cls) -> "EmbeddingMatcher":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_model(self):
        if not self._available:
            return None
        if self._model is None:
            logger.info(f"📦 Loading model '{MODEL_NAME}' (first call, ~5s) …")
            self._model = _sentence_transformers(MODEL_NAME)
            logger.info("✅ Embedding model ready.")
        return self._model

    def index(self, names: list[str]) -> None:
        """
        Pre-compute embeddings for the full nutrition catalogue.
        Call this once when the catalogue changes — O(N) encoding.
        """
        model = self._get_model()
        if model is None or not names:
            return
        logger.info(f"🔢 Indexing {len(names)} nutrition names …")
        vecs = model.encode(names, normalize_embeddings=True, show_progress_bar=False)
        self._index_names = names
        self._index_vecs = np.array(vecs, dtype=np.float32)
        logger.info("✅ Nutrition index ready.")

    def find_best(
        self,
        query: str,
        threshold: float = EMBEDDING_THRESHOLD,
    ) -> Optional[tuple[str, float]]:
        """
        Find the most semantically similar nutrition name for a product query.

        Returns:
            (best_nutrition_name, cosine_similarity_0_to_1) or None.
        """
        model = self._get_model()
        if model is None or self._index_vecs is None or not query:
            return None

        q_vec = model.encode([query], normalize_embeddings=True)[0]
        # Cosine similarity = dot product of normalised vectors
        sims = self._index_vecs @ q_vec
        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])

        if best_score < threshold:
            return None

        return self._index_names[best_idx], round(best_score, 4)

    def find_top_k(
        self,
        query: str,
        k: int = 5,
        threshold: float = EMBEDDING_THRESHOLD,
    ) -> list[tuple[str, float]]:
        """Return top-k matches above threshold, sorted by similarity desc."""
        model = self._get_model()
        if model is None or self._index_vecs is None or not query:
            return []

        q_vec = model.encode([query], normalize_embeddings=True)[0]
        sims = self._index_vecs @ q_vec

        # Get indices of top-k
        top_indices = np.argsort(sims)[::-1][:k]
        return [
            (self._index_names[i], round(float(sims[i]), 4))
            for i in top_indices
            if sims[i] >= threshold
        ]

    @property
    def is_ready(self) -> bool:
        return self._available and self._index_vecs is not None
