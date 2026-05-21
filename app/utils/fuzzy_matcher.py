"""
utils/fuzzy_matcher.py
──────────────────────
Fuzzy string matching between product normalized_names and nutrition keys.

Algorithm choice — why rapidfuzz over difflib/fuzzywuzzy:
  • 10-100x faster (C++ implementation)
  • token_sort_ratio handles word-order differences:
      "breast chicken" ↔ "chicken breast" → 100
  • token_set_ratio handles subset matches:
      "fresh red tomato" ↔ "tomato" → high score

Scoring strategy (layered):
  1. Exact match         → confidence 1.0
  2. token_sort_ratio    → catches word reordering
  3. token_set_ratio     → catches subset/superset names
  4. partial_ratio       → catches truncated names
  → Final score = weighted max of the three
"""

from rapidfuzz import fuzz, process
from typing import Optional


# Minimum score (0–100) to consider a match valid
FUZZY_THRESHOLD = 72


def _score(a: str, b: str) -> float:
    """
    Composite fuzzy score between two normalised strings.
    Returns a value in [0, 100].
    """
    if not a or not b:
        return 0.0

    # Exact match shortcut
    if a == b:
        return 100.0

    sort  = fuzz.token_sort_ratio(a, b)
    set_  = fuzz.token_set_ratio(a, b)
    part  = fuzz.partial_ratio(a, b)

    # Weighted combination: set_ catches subsets well, sort catches reorders
    return max(sort * 0.4 + set_ * 0.4 + part * 0.2,
               sort,
               set_)


def _to_confidence(raw_score: float) -> float:
    """Convert a 0–100 rapidfuzz score to a 0–1 confidence float."""
    return round(raw_score / 100.0, 4)


def find_best_fuzzy_match(
    query: str,
    candidates: list[str],
    threshold: int = FUZZY_THRESHOLD,
) -> Optional[tuple[str, float]]:
    """
    Find the best fuzzy match for `query` among `candidates`.

    Returns:
        (best_candidate, confidence_0_to_1) if above threshold, else None.
    """
    if not query or not candidates:
        return None

    # rapidfuzz.process.extractOne is fast even over 10k candidates
    result = process.extractOne(
        query,
        candidates,
        scorer=fuzz.token_set_ratio,
        score_cutoff=threshold,
    )

    if result is None:
        return None

    best_str, raw_score, _ = result

    # Refine with composite score
    composite = _score(query, best_str)
    if composite < threshold:
        return None

    return best_str, _to_confidence(composite)


def batch_fuzzy_match(
    queries: list[str],
    candidates: list[str],
    threshold: int = FUZZY_THRESHOLD,
) -> dict[str, Optional[tuple[str, float]]]:
    """
    Match every query against all candidates.
    Returns dict: { query → (best_match, confidence) | None }
    """
    results = {}
    for q in queries:
        results[q] = find_best_fuzzy_match(q, candidates, threshold)
    return results
