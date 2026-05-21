"""
utils/normalizer.py
───────────────────
Cleans and normalises product names so fuzzy matching and
embedding similarity work on a consistent, noise-free string.

Design decisions
────────────────
• Arabic text is stripped (market names often mix langs) — the
  embedding model handles Arabic natively; the fuzzy layer works
  best on cleaned ASCII/English tokens.
• Units (kg, g, ml, l, oz, lb) are removed — we only want the
  food concept, not the packaging size.
• Brand tokens are NOT removed here; that's the matching engine's job.
"""

import re
import unicodedata


# Tokens that add no semantic value to the food name
_NOISE_TOKENS = {
    "fresh", "imported", "local", "organic", "natural", "premium",
    "frozen", "chilled", "packed", "washed", "ready", "extra",
    "super", "special", "new", "best", "quality", "product",
    "egypt", "egyptian", "saudi", "turkish",
}

_UNIT_RE = re.compile(
    r"\b(\d+[\.,]?\d*)\s*(kg|g|gr|gm|ml|l|ltr|oz|lb|lbs|pcs|pc|pack|pkt)\b",
    re.IGNORECASE,
)

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F]+")
_NON_ALPHA  = re.compile(r"[^a-z0-9\s]")
_WHITESPACE = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """
    Returns a lowercase, noise-free product name suitable for matching.

    Steps:
    1. Unicode NFKC normalisation (é → e, ½ → 1/2, etc.)
    2. Strip Arabic characters
    3. Remove unit expressions  (500g, 1kg, 2ltr …)
    4. Lowercase
    5. Remove non-alphanumeric characters
    6. Remove noise stop-words
    7. Collapse whitespace and strip
    """
    if not raw:
        return ""

    # 1. Unicode normalise
    text = unicodedata.normalize("NFKC", raw)

    # 2. Remove Arabic
    text = _ARABIC_RE.sub(" ", text)

    # 3. Remove units
    text = _UNIT_RE.sub(" ", text)

    # 4. Lowercase
    text = text.lower()

    # 5. Keep only alphanumeric + spaces
    text = _NON_ALPHA.sub(" ", text)

    # 6. Remove noise tokens
    tokens = [t for t in text.split() if t not in _NOISE_TOKENS and len(t) > 1]

    # 7. Collapse
    return _WHITESPACE.sub(" ", " ".join(tokens)).strip()


def normalize_rows(rows: list[tuple]) -> list[tuple]:
    """
    Adds the normalized_name field to scraper rows.
    Input row:  (source, sku, category, product_name, price)
    Output row: (source, sku, category, product_name, normalized_name, price)
    """
    out = []
    for source, sku, category, name, price in rows:
        out.append((source, sku, category, name, normalize_name(name), price))
    return out
