"""
Appended to routers/optimizer.py
─────────────────────────────────
POST /optimize/meal-search
Uses MiniLM semantic similarity to find matching recipes by name.
"""

from pydantic import BaseModel
from typing import Optional
import json
import logging

from app.services.recipe_optimizer import optimize_recipe

logger = logging.getLogger("nutribudget.meal_search")


# ── Standard unit weights for items normally counted, not weighed ────────────
# Maps ingredient_key → (grams_per_unit, arabic_unit_name, english_unit_name).
# Used purely for UI display: when an ingredient has a known unit weight, we
# annotate the response with how many "units" the recipe's gram amount equals,
# so users see "3 بيضات" next to "150g". The optimizer math stays in grams.
INGREDIENT_UNITS: dict[str, tuple[float, str, str]] = {
    "eggs":          (60,  "بيضة",   "egg"),
    "egg":           (60,  "بيضة",   "egg"),
    "garlic_clove":  (3,   "فص",     "clove"),
    "garlic":        (3,   "فص",     "clove"),
    "bread":         (80,  "رغيف",   "loaf"),
    "bread_baladi":  (80,  "رغيف",   "loaf"),
    "pita":          (80,  "رغيف",   "loaf"),
    "onion":         (110, "بصلة",   "onion"),
    "tomato":        (120, "طماطمة", "tomato"),
    "lemon":         (60,  "ليمونة", "lemon"),
    "potato":        (170, "بطاطس",  "potato"),
    "carrot":        (60,  "جزرة",   "carrot"),
    "cucumber":      (200, "خيارة",  "cucumber"),
    "pepper":        (150, "فلفل",   "pepper"),
    "banana":        (120, "موزة",   "banana"),
    "apple":         (180, "تفاحة",  "apple"),
    "orange":        (130, "برتقالة","orange"),
    "cheese_triangle": (15, "مثلث",  "triangle"),
}


def annotate_unit(ingredient_name: str, weight_g: float) -> Optional[dict]:
    """
    Return a {unit_count, unit_label_ar, unit_label_en, grams_per_unit} dict
    if this ingredient has a known unit weight, else None.
    """
    if not weight_g or weight_g <= 0:
        return None
    info = INGREDIENT_UNITS.get(ingredient_name.lower())
    if not info:
        return None
    grams_per_unit, ar, en = info
    count = round(weight_g / grams_per_unit, 1)
    if count <= 0:
        return None
    # Pluralise mildly for English; Arabic singular is fine for chip display
    return {
        "unit_count":       count,
        "unit_label_ar":    ar,
        "unit_label_en":    en + ("s" if count >= 2 else ""),
        "grams_per_unit":   grams_per_unit,
    }


def _parse_weight_from_name(product_name: str, ingredient_key: str, db_weight: float) -> float:
    """
    Recover true pack weight from the product name when the DB value is the
    default placeholder (1000g).  Uses ingredient-specific rules:

    Eggs  : count the eggs ("30 Eggs", "6 Pieces", …) × 60g/egg
    Generic: look for explicit weight tokens ("500g", "1kg", "1.5 L", …)

    Falls back to db_weight (even if it's 1000) only when nothing can be
    parsed, so we never introduce a worse value.
    """
    import re
    name = product_name or ""

    # ── Eggs: parse count ──────────────────────────────────────────────────
    if ingredient_key == "eggs":
        m = re.search(r'(\d+)\s*(?:Eggs?|Pieces?|Pcs?|بيضة)', name, re.IGNORECASE)
        if m:
            count = int(m.group(1))
            return count * 60.0              # ~60g per standard egg

    # ── Generic: weight token in name ────────────────────────────────────
    # Matches: "500g", "1 kg", "1.5L", "200 ml", etc.
    m = re.search(
        r'(\d+(?:\.\d+)?)\s*'
        r'(kg|g|l|ml|liter|litre|جرام|كيلو)',
        name, re.IGNORECASE
    )
    if m:
        val, unit = float(m.group(1)), m.group(2).lower()
        if unit in ("kg", "كيلو"):
            return val * 1000.0
        elif unit in ("l", "liter", "litre"):
            return val * 1000.0             # 1L ≈ 1000g for liquids
        elif unit in ("ml",):
            return val                      # ml → g (approx)
        else:                               # g or جرام
            return val

    # ── Fallback: use whatever the DB has ────────────────────────────────
    return db_weight if db_weight > 0 else 1000.0


class MealSearchRequest(BaseModel):
    query:      str
    budget_egp: Optional[float] = None
    protein_g:  Optional[float] = None
    top_k:      int = 5


# ── Translation: EN → list[AR] (longest match wins) ─────────────────────────
TRANSLITERATION: dict[str, list[str]] = {
    # Multi-word first (longest match wins)
    "club sandwich":    ["كلوب ساندويتش", "كلوب ساندوتش"],
    "grilled chicken":  ["فراخ مشوية", "دجاج مشوي"],
    "fried chicken":    ["فراخ مقلية", "دجاج مقلي"],
    "roast chicken":    ["فراخ محمرة"],
    "chicken soup":     ["شوربة فراخ", "شوربة دجاج"],
    "fried fish":       ["سمك مقلي"],
    "grilled fish":     ["سمك مشوي"],
    "fish soup":        ["شوربة سمك"],
    "lentil soup":      ["شوربة عدس"],
    "om ali":           ["أم علي"],
    "umm ali":          ["أم علي"],
    "hot dog":          ["هوت دوج"],
    "ice cream":        ["آيس كريم"],
    "caesar salad":     ["سيزار سالاد", "سيزار"],
    "seafood":          ["مأكولات بحرية"],
    # Single words
    "koshary":  ["كشري"], "koshari":  ["كشري"], "koshery": ["كشري"],
    "kushari":  ["كشري"], "kushary":  ["كشري"],
    "foul":     ["فول"],  "ful":      ["فول"],  "fool":    ["فول"],
    "taameya":  ["طعمية"],"tamiya":   ["طعمية"],
    "falafel":  ["طعمية", "فلافل"],
    "shawarma": ["شاورما"],"shawurma": ["شاورما"],
    "kofta":    ["كفتة"], "kafta":    ["كفتة"], "kefta":   ["كفتة"],
    "molokhia": ["ملوخية"],"mulukhiyah":["ملوخية"],
    "mahshi":   ["محشي"], "mahshy":   ["محشي"],
    "fatah":    ["فتة"],  "fatta":    ["فتة"],  "fattah":  ["فتة"],
    "kebab":    ["كباب"],
    "feteer":   ["فطير"], "fiteer":   ["فطير"],
    "konafa":   ["كنافة"],"kunafa":   ["كنافة"],
    "basbousa": ["بسبوسة"],
    "chicken":  ["فراخ", "دجاج"],
    "pasta":    ["مكرونة", "ماكرونة"], "macaroni": ["مكرونة"],
    "pizza":    ["بيتزا"],
    "liver":    ["كبدة"],
    "fish":     ["سمك"],
    "grilled":  ["مشوي", "مشوية"],
    "soup":     ["شوربة"],
    "salad":    ["سلطة"],
    "rice":     ["أرز"],
    "eggs":     ["بيض"],   "egg":     ["بيض"],
    "omelette": ["عجة"],
    "lentils":  ["عدس"],   "lentil":  ["عدس"],
    "beans":    ["فاصوليا"],
    "burger":   ["برجر"],
    "sandwich": ["ساندويتش", "ساندوتش", "سندوتش"],
    "steak":    ["ستيك"],
    "lamb":     ["لحم ضاني", "ضاني"],
    "beef":     ["لحم بقري", "لحمة"],
    "okra":     ["بامية", "ويكة"],
    "eggplant": ["باذنجان"],
    "spinach":  ["سبانخ"],
    "potato":   ["بطاطس"],
    "hawawshi": ["هواوشي", "حواوشي"],
    "sayadeya": ["صيادية"], "sayadiyya": ["صيادية"],
    "sobia":    ["سوبيا"],
    "bread":    ["عيش", "خبز"],
    "pita":     ["عيش"],
    "cheese":   ["جبنة", "جبن"],
    "milk":     ["حليب", "لبن"],
    "yogurt":   ["زبادي"],
    "cream":    ["قشطة", "كريمة"],
    "cake":     ["كيك"],
    "baklava":  ["بقلاوة"],
    "cookie":   ["كوكيز"],
    "brownie":  ["براوني"],
    "croissant":["كرواسون"],
    "waffle":   ["وافل"],
    "pancake":  ["بانكيك"],
    "sushi":    ["سوشي"],
    "taco":     ["تاكو"],
    "pigeon":   ["حمام"],
    "duck":     ["بط"],
    "rabbit":   ["أرنب"],
    "shrimp":   ["جمبري"],
    "tuna":     ["تونة"],
    "mushroom": ["فطر", "مشروم"],
    "avocado":  ["أفوكادو"],
    "stuffed":  ["محشي", "محشية"],
    "baked":    ["بالفرن"],
    "fried":    ["مقلي", "مقلية"],
}


import time as _time

# ── Embedding Cache (avoids re-encoding 332 recipes on every search) ─────────
class _EmbCache:
    TTL = 300  # 5 minutes

    def __init__(self):
        self.recipe_rows:    list  = []
        self.recipe_names:   list  = []
        self.recipe_embs           = None
        self.product_map:    dict  = {}
        self.ing_keys:       list  = []
        self.ing_embs              = None
        self._ts_rec:  float = 0.0
        self._ts_prod: float = 0.0

    @property
    def recipes_ok(self): return self.recipe_embs is not None and _time.time()-self._ts_rec < self.TTL
    @property
    def products_ok(self): return bool(self.product_map) and _time.time()-self._ts_prod < self.TTL

    def save_recipes(self, rows, names, embs):
        self.recipe_rows=rows; self.recipe_names=names; self.recipe_embs=embs
        self._ts_rec = _time.time()

    def save_products(self, pmap, keys, embs):
        self.product_map=pmap; self.ing_keys=keys; self.ing_embs=embs
        self._ts_prod = _time.time()

    def clear(self): self.recipe_embs=None; self.ing_embs=None; self._ts_rec=0; self._ts_prod=0

_cache = _EmbCache()

def normalize_ar(text: str) -> str:
    """Normalize Arabic text for matching."""
    import re
    text = re.sub(r"[أإآٱ]", "ا", text)
    text = re.sub(r"[ىئ]", "ي", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"[\u064B-\u065F]", "", text)
    return re.sub(r"\s+", " ", text).strip()




# ── Bilingual Recipe Index ────────────────────────────────────────────────────
def _build_recipe_index(recipe_names: list[str]) -> dict[str, list[str]]:
    """
    Build reverse map: for each Arabic recipe name → list of EN search tokens.
    So "grilled chicken" matches "فراخ مشوية" even if not in TRANSLITERATION.
    """
    # Reverse TRANSLITERATION: ar_word → [en_keys]
    reverse_map: dict[str, list[str]] = {}
    for en_key, ar_list in TRANSLITERATION.items():
        for ar in ar_list:
            ar_norm = normalize_ar(ar)
            # index each word separately too
            for ar_word in ar_norm.split():
                if len(ar_word) >= 2:
                    reverse_map.setdefault(ar_word, []).append(en_key)
            # and the full phrase
            reverse_map.setdefault(ar_norm, []).append(en_key)

    index: dict[str, list[str]] = {}
    for name in recipe_names:
        name_norm = normalize_ar(name)
        en_tokens: list[str] = []
        # Full name match
        if name_norm in reverse_map:
            en_tokens.extend(reverse_map[name_norm])
        # Word-by-word
        for word in name_norm.split():
            if len(word) >= 2 and word in reverse_map:
                en_tokens.extend(reverse_map[word])
        index[name] = list(dict.fromkeys(en_tokens))
    return index


def _score_recipe(query_lower: str, name_norm: str,
                  all_alts_norm: list[str],
                  all_alts_words: list[list[str]],
                  en_tokens: list[str]) -> tuple[bool, bool, bool]:
    """
    Returns (tier1, tier2, tier3).
    Checks Arabic alternatives AND English tokens from bilingual index.
    """
    q_words_en = [w for w in query_lower.split() if len(w) >= 2]

    # Arabic side
    ar1 = any(alt in name_norm for alt in all_alts_norm)
    ar2 = any(words and all(w in name_norm for w in words) for words in all_alts_words)
    ar3 = any(words and any(w in name_norm for w in words) for words in all_alts_words)

    # English side — user typed English, we check against recipe EN tokens
    en1 = query_lower in en_tokens
    en2 = bool(q_words_en) and all(any(qw in et for et in en_tokens) for qw in q_words_en)
    en3 = bool(q_words_en) and any(any(qw in et for et in en_tokens) for qw in q_words_en)

    t1 = ar1 or en1
    t2 = (not t1) and (ar2 or en2)
    t3 = (not t1) and (not t2) and (ar3 or en3)
    return t1, t2, t3

def _translate_query(query: str) -> tuple[str, list[str]]:
    """
    Translate English food query to Arabic.
    Returns (primary_translation, all_alternatives).
    Longest match wins — "club sandwich" beats "sandwich".
    """
    q = query.strip().lower()
    sorted_keys = sorted(TRANSLITERATION.keys(), key=len, reverse=True)
    primary  = None
    all_alts = []
    # 1. Exact full match
    if q in TRANSLITERATION:
        alts = TRANSLITERATION[q]
        primary = alts[0]; all_alts.extend(alts)
    # 2. Longest substring match
    if not primary:
        for key in sorted_keys:
            if key in q:
                alts = TRANSLITERATION[key]
                primary = alts[0]; all_alts.extend(alts); break
    # 3. Word-by-word — add all partial matches as alternatives
    for word in q.split():
        if word in TRANSLITERATION:
            all_alts.extend(TRANSLITERATION[word])
    all_alts = list(dict.fromkeys(all_alts))  # deduplicate, preserve order
    return (primary, all_alts) if primary else (query, all_alts)


async def _search_meals(query: str, db, top_k: int = 5, budget_egp: float = 0) -> list[dict]:
    """Semantic search over recipe names using MiniLM."""
    from sqlalchemy import text
    from app.services.nlp_parser import _NLPModel
    import numpy as np

    # Translate English queries to Arabic — returns (primary, all_alternatives)
    primary_query, all_alternatives = _translate_query(query)
    search_query = primary_query

    # Load all recipes
    rows = (await db.execute(text(
        "SELECT recipe_id, recipe_name, meal_type, ingredients_json, instructions, prep_time FROM recipes"
    ))).fetchall()

    if not rows:
        return []

    recipe_names = [r.recipe_name for r in rows]

    # Precompute normalized alternatives for tier matching
    all_alts_norm  = [normalize_ar(a) for a in all_alternatives]
    all_alts_words = [[w for w in normalize_ar(a).split() if len(w) >= 2] for a in all_alternatives]

    try:
        model = _NLPModel.get()
        query_vec = model.encode([search_query], convert_to_numpy=True)[0]

        # Recipe embeddings: use cache if valid, else encode + cache
        if _cache.recipes_ok and _cache.recipe_names == recipe_names:
            recipe_vecs = _cache.recipe_embs
            logger.debug("🚀 Using cached recipe embeddings")
        else:
            recipe_vecs = model.encode(recipe_names, convert_to_numpy=True)
            _cache.save_recipes(rows, recipe_names, recipe_vecs)
            logger.info("📦 Recipe embeddings cached (%d recipes)", len(recipe_names))

        q_norm  = normalize_ar(search_query)
        q_words = [w for w in q_norm.split() if len(w) >= 2]
        query_lower = query.strip().lower()

        # Build bilingual index: AR recipe name → EN tokens (once per recipe set)
        recipe_index = _build_recipe_index(recipe_names)

        scores = []
        for i, rvec in enumerate(recipe_vecs):
            name_norm  = normalize_ar(recipe_names[i])
            en_tokens  = recipe_index.get(recipe_names[i], [])

            # Score using both Arabic alternatives AND bilingual EN tokens
            tier1, tier2, tier3 = _score_recipe(
                query_lower, name_norm,
                all_alts_norm, all_alts_words,
                en_tokens
            )
            # Also check q_norm directly (Arabic input case)
            if not tier1 and q_norm and q_norm in name_norm:
                tier1 = True; tier2 = False; tier3 = False

            if tier1:
                sim = 0.98
            elif tier2:
                sim = 0.90
            elif tier3:
                dot  = float(np.dot(query_vec, rvec))
                nrm  = float(np.linalg.norm(query_vec) * np.linalg.norm(rvec))
                sim  = min(0.89, (dot / nrm if nrm > 0 else 0.0) + 0.25)
            else:
                # ── Tier 4: Pure semantic — hard cap 0.55 ─────────────────
                dot  = float(np.dot(query_vec, rvec))
                nrm  = float(np.linalg.norm(query_vec) * np.linalg.norm(rvec))
                sim  = min(dot / nrm if nrm > 0 else 0.0, 0.55)

            scores.append((sim, i))

        scores.sort(reverse=True)
        top_indices = [i for _, i in scores[:top_k * 3]]

    except Exception as e:
        logger.warning(f"MiniLM unavailable: {e}, using keyword fallback")
        def _kw_match(name):
            n = normalize_ar(name)
            return (any(a in n for a in all_alts_norm) or
                    any(w in n for ws in all_alts_words for w in ws))
        top_indices = [i for i, name in enumerate(recipe_names) if _kw_match(name)][:top_k]
        scores = [(1.0, i) for i in top_indices]

    # Get cost/macros from ingredient_product_map (multi-brand)
    # ─── Pre-mapped products only ────────────────────────────────────────────
    # Each ingredient already has 10–120 explicitly mapped products in
    # ingredient_product_map (e.g. rice=99, pasta=121, lentils=11). That gives
    # us the multi-brand pool we need for budget-aware selection.
    #
    # ⚠️ DO NOT re-add a category-based UNION ALL here. Egyptian supermarket
    # categories are too coarse — "Grains & Legumes" mixes rice, lentils,
    # pasta AND instant noodles, and "Oils & Condiments" mixes oils, sauces
    # and salt. A category JOIN pulls Indomie under rice/lentils/pasta and
    # salt under tomato_sauce, which is exactly the bug this comment exists
    # to prevent.
    #
    # ─── Pre-mapped products only ────────────────────────────────────────────
    # Each ingredient already has 10–120 explicitly mapped products in
    # ingredient_product_map (e.g. rice=99, pasta=121, lentils=11). That gives
    # us the multi-brand pool we need for budget-aware selection.
    #
    # ⚠️ DO NOT re-add a category-based UNION ALL here. Egyptian supermarket
    # categories are too coarse — "Grains & Legumes" mixes rice, lentils,
    # pasta AND instant noodles, and "Oils & Condiments" mixes oils, sauces
    # and salt. A category JOIN pulls Indomie under rice/lentils/pasta and
    # salt under tomato_sauce, which is exactly the bug this comment exists
    # to prevent.
    #
    # ✅ LEFT JOIN to fresh_products — for ingredients where the mapping was
    # populated as an "Estimated" entry (eggs, salt, cheese, broth, fresh
    # molokhia, rabbit, …) there's no scraped SKU to join against, so the
    # JOIN would silently drop them.
    #
    # ⚠️ Defensive price_per_100g — never trust the stored value. A bug in
    # the migration script wrote eggs as 6.78 EGP / 1800g (≈0.38 EGP/100g)
    # even though real 30-egg cartons are ~120-145 EGP. So we always
    # *recompute* price_per_100g from price/weight at query time, and only
    # fall back to the stored value when both price and weight are missing.
    #
    # ✅ UNION with real fresh_products via ingredient_keywords — for
    # generic estimated ingredients (eggs, milk, cheese, butter, salt …)
    # we also pull every product whose name contains a known keyword,
    # so the user sees real brands at real prices instead of a 6.78 EGP
    # placeholder.
    map_sql = text("""
        SELECT
            m.ingredient_key,
            -- Defensive recalc: prefer fresh_products price/weight, then mapping
            CASE
                WHEN COALESCE(fp.price, m.price_egp) > 0
                 AND COALESCE(fp.unit_weight_g, m.unit_weight_g, 0) > 0
                THEN (COALESCE(fp.price, m.price_egp)
                      / COALESCE(fp.unit_weight_g, m.unit_weight_g)) * 100
                ELSE m.price_per_100g
            END                                                   AS price_per_100g,
            COALESCE(fp.product_name, m.product_name)             AS product_name,
            COALESCE(fp.source,       m.source)                   AS source,
            COALESCE(fp.price,        m.price_egp)                AS price_egp,
            COALESCE(fp.unit_weight_g, m.unit_weight_g, 1000)     AS unit_weight_g,
            (fp.sku IS NULL)                                      AS is_estimated,
            COALESCE(m.is_primary, 1)                             AS is_primary,
            COALESCE(n.display_name, m.ingredient_key)            AS display_name,
            COALESCE(n.calories_per_100g, 0)                      AS calories_per_100g,
            COALESCE(n.protein_g, 0)                              AS protein_g,
            COALESCE(n.carbs_g, 0)                                AS carbs_g,
            COALESCE(n.fats_g, 0)                                 AS fats_g
        FROM ingredient_product_map m
        LEFT JOIN nutrition_facts n   ON n.normalized_name = m.ingredient_key
        LEFT JOIN fresh_products fp   ON fp.sku = m.sku AND fp.source = m.source
        WHERE COALESCE(fp.price, m.price_egp) > 0
          AND COALESCE(fp.unit_weight_g, m.unit_weight_g, 0) > 0
          -- Exclude implausible mappings: beverages or tiny samples
          AND (COALESCE(fp.price, m.price_egp)
               / COALESCE(fp.unit_weight_g, m.unit_weight_g)) * 100 <= 300
    """)
    # ── Product map: use cache if valid ─────────────────────────────────────
    _use_cached_products = _cache.products_ok
    if _use_cached_products:
        all_products_map   = dict(_cache.product_map)
        logger.debug("🚀 Using cached product map (%d ingredients)", len(all_products_map))

    if not _use_cached_products:
      try:
        all_map_rows = (await db.execute(map_sql)).fetchall()
      except Exception:
        # Fallback to simple query if fresh_products schema differs
        fallback_sql = text("""
            SELECT m.ingredient_key,
                   CASE WHEN m.price_egp > 0 AND m.unit_weight_g > 0
                        THEN (m.price_egp / m.unit_weight_g) * 100
                        ELSE m.price_per_100g END                  AS price_per_100g,
                   m.product_name, m.source, m.price_egp,
                   COALESCE(m.unit_weight_g, 1000)                 AS unit_weight_g,
                   1                                               AS is_estimated,
                   COALESCE(m.is_primary, 1)                        AS is_primary,
                   COALESCE(n.display_name, m.ingredient_key)      AS display_name,
                   COALESCE(n.calories_per_100g, 0)                AS calories_per_100g,
                   COALESCE(n.protein_g, 0)                        AS protein_g,
                   COALESCE(n.carbs_g, 0)                          AS carbs_g,
                   COALESCE(n.fats_g, 0)                           AS fats_g
            FROM ingredient_product_map m
            LEFT JOIN nutrition_facts n ON n.normalized_name = m.ingredient_key
            WHERE m.price_egp > 0 AND m.unit_weight_g > 0
        """)
        all_map_rows = (await db.execute(fallback_sql)).fetchall()

    # Build ALL products map — only when NOT using cache
    if not _use_cached_products:
        all_products_map = {}   # ingredient_key → [list of all products sorted by price ASC]

        for r in all_map_rows:
            key = r.ingredient_key
            # is_estimated may come back as bool/int/None depending on driver
            try:
                is_est = bool(getattr(r, "is_estimated", 0)) if not isinstance(
                    getattr(r, "is_estimated", 0), str
                ) else getattr(r, "is_estimated", "0") not in ("0", "", "false", "False")
            except Exception:
                is_est = False

            price_egp  = float(r.price_egp) if hasattr(r, 'price_egp') else 0
            db_weight  = float(r.unit_weight_g or 0)
            weight = _parse_weight_from_name(r.product_name, key, db_weight)
            ppg = (price_egp / weight * 100) if (price_egp > 0 and weight > 0) else float(r.price_per_100g)

            entry = {
                "price_per_100g": ppg,
                "display_name":   r.display_name or key.replace("_"," ").title(),
                "product_name":   r.product_name,
                "source":         r.source,
                "price_egp":      price_egp,
                "unit_weight_g":  weight,
                "calories":       float(r.calories_per_100g),
                "protein":        float(r.protein_g),
                "carbs":          float(r.carbs_g),
                "fats":           float(r.fats_g),
                "is_estimated":   is_est,
                "is_primary":     (int(getattr(r, "is_primary", 1) or 0) == 1),
            }
            all_products_map.setdefault(key, []).append(entry)

    # ─── Keyword backfill for est-only ingredients ──────────────────────────
    # For generic ingredients whose only mapping is an "Estimated" placeholder
    # (eggs, milk, butter, cheese, salt …) try to backfill from fresh_products
    # using product-name keywords. This pulls REAL brands at REAL prices into
    # the multi-brand pool — only for ingredients that don't already have
    # real options.
    #
    # ⚠️ Use precise patterns with % only at the END (not start) to avoid
    # partial-word false positives: "Egg%" matches Eggs but not Eggplant;
    # "% Eggs" matches "Royal White Eggs" but not "Reggina Alphabets".
    # Where a keyword is ambiguous, prefer the Arabic or a suffix-bounded form.
    # keyword_backfill: key → (include_patterns, exclude_patterns, ppg_floor, ppg_ceil)
    keyword_backfill = {
        "eggs":        (["% Eggs%","% White Eggs%","% Brown Eggs%","% Fresh Eggs%","بيض%"],
                        ["Eggplant","Egg Noodle","Custard","Powder","Liquid"],                          3.0, 20.0),
        "salt":        (["% Salt%","% Sea Salt%","% Rock Salt%","% Table Salt%","ملح%"],
                        ["Salted","Salt & Vinegar","Seasoning","Flavored"],                             0.05, 5.0),
        "cheese":      (["% Cheese%","جبن%","جبنة%","% Feta%","% Cheddar%","% Mozzarella%","% White Cheese%"],
                        ["Cheese Flavor","Cheese Powder","Cheese Puff","Cheese Cracker","Cheese Snack",
                         "Popcorn","Chips","Doritos","Cheetos","Flavored","Dressing"],                  4.0, 100.0),
        "milk":        (["% Milk%","% Full Fat Milk%","% Fresh Milk%","% UHT Milk%","حليب%","لبن%"],
                        ["Milk Chocolate","Milk Tea","Milkshake Powder","Condensed",
                         "Energy","Vitamin","Supplement","Flavored"],                                   1.0, 30.0),
        "butter":      (["% Butter%","% Fern Butter%","% Ghee%","% Clarified Butter%","زبدة%","سمن%"],
                        ["Butter Flavor","Butter Popcorn","Peanut Butter","Almond Butter","Flavored"],  8.0, 80.0),
        "yogurt":      (["% Yoghurt%","% Yogurt%","% Plain Yogurt%","% Natural Yogurt%","زبادي%"],
                        ["Yogurt Flavor","Yogurt Drink","Strawberry Yogurt","Fruit Yogurt",
                         "Flavored","Drinking Yogurt","Energy"],                                        2.0, 30.0),
        "cream":       (["% Cooking Cream%","% Whipping Cream%","% Heavy Cream%","% Fresh Cream%",
                         "% Double Cream%","كريمة طبخ%","كريمة خفق%"],
                        ["Ice Cream","Cream Cheese","Cream Soda","Cream Biscuit","Cream Wafer",
                         "Chocolate Cream","Vanilla Cream","Strawberry Cream","Body Cream","Skin"],     3.0, 60.0),
        "honey":       (["% Pure Honey%","% Natural Honey%","% Raw Honey%","% Sidr Honey%",
                         "% Clover Honey%","% Blossom Honey%","عسل نحل%","عسل طبيعي%"],
                        ["Honey Flavor","Honey Nut","Honey Wheat","Honey Cereal","Honey Rings",
                         "Honey Loops","Honey Pops","Honey Bun","Honey Cake","Honey Mustard",
                         "Honey Glaze","Honey Wax","Corn Flakes","Cereal","Granola","Muesli",
                         "Bar","Energy","Drink","Flavored"],                                            10.0, 200.0),
        "sugar":       (["% Sugar%","% White Sugar%","% Cane Sugar%","% Refined Sugar%","سكر%"],
                        ["Sugar Free","Sugar Flavor","Sugar Coated","Candy","Chocolate","Flavored"],    0.5, 10.0),
        "flour":       (["% Wheat Flour%","% All Purpose Flour%","% Plain Flour%",
                         "% Bread Flour%","% Cake Flour%","دقيق قمح%","دقيق%"],
                        ["Tortilla","Flour Tortilla","Almond Flour","Coconut Flour",
                         "Chickpea Flour","Premix","Pancake Mix","Bread Mix",
                         "Cracker","Wafer","Biscuit","Cookie","Flavored"],                              0.5, 15.0),
        "beef":        (["% Beef%","% Minced Beef%","% Beef Cubes%","% Beef Steak%","لحم بقري%","لحمة%"],
                        ["Beef Flavor","Beef Chips","Beef Jerky","Beef Snack","Beef Bouillon",
                         "Noodles","Instant Soup","Flavored"],                                          30.0, 200.0),
        "minced_beef": (["% Minced Beef%","% Ground Beef%","لحمة مفرومة%"],
                        ["Flavor","Stock","Bouillon","Instant","Snack"],                                30.0, 150.0),
        "ground_beef": (["% Minced Beef%","% Ground Beef%","لحمة مفرومة%"],
                        ["Flavor","Stock","Bouillon","Instant","Snack"],                                30.0, 150.0),
        "lamb":        (["% Lamb%","ضاني%","خروف%","% Mutton%"],
                        ["Lamb Flavor","Lamb Chips","Lamb Snack","Lamb Bouillon","Instant","Flavored"], 40.0, 250.0),
        "ground_lamb": (["% Minced Lamb%","% Ground Lamb%","ضاني مفروم%"],["Flavor","Stock","Instant"],40.0, 250.0),
        "minced_lamb": (["% Minced Lamb%","ضاني مفروم%"],                  ["Flavor","Stock","Instant"],40.0, 250.0),
        "lamb_ribs":   (["% Lamb Rack%","% Lamb Rib%","ريش ضاني%"],        ["Flavor","Stock"],          40.0, 250.0),
        "lamb_chops":  (["% Lamb Chop%","ريش ضاني%"],                      ["Flavor","Stock"],          40.0, 250.0),
        "lamb_whole":  (["% Whole Lamb%","ضاني%","خروف%"],                  ["Flavor","Instant"],        40.0, 250.0),
        "fish":        (["% Tilapia%","% Fish Fillet%","% Frozen Fish%","% Fresh Fish%","% Whole Fish%","% بلطي%"],
                        ["Fish Flavor","Fish Snack","Fish Crackers","Fish Sauce","Fish Stock",
                         "Energy Drink","Vitamin","Supplement","Flavored"],                             15.0, 200.0),
        "fish_fillet": (["% Fish Fillet%","% Fillet%","فيليه سمك%"],       ["Flavor","Sauce","Stock"],  15.0, 200.0),
        "shrimp":      (["% Shrimp%","% Prawns%","جمبري%"],
                        ["Shrimp Flavor","Chips","Energy Drink","Flavored"],                            60.0, 200.0),
        "liver":       (["% Liver%","% Chicken Liver%","كبدة%"],
                        ["Liver Flavor","Paste","Spread","Snack"],                                      10.0, 100.0),
        "bread":       (["% Balady Bread%","% Lebanese Bread%","% Pita Bread%","% Whole Wheat Bread%","عيش%","خبز%"],
                        ["Bread Crumbs","Bread Mix","Bread Flavor","Tortilla","Cracker","Wafer"],        5.0, 50.0),
        "bread_baladi":(["% Balady Bread%","عيش بلدي%"],                   ["Crumbs","Mix","Flavor"],    5.0, 30.0),
        "toast_bread": (["% Plain Toast%","% Milk Toast%","% Whole Weight Toast%","تواست%"],
                        ["Flavor","Mix","Crumbs"],                                                       5.0, 30.0),
        "bread_roll":  (["% Soft Roll%","% Petit Pain%","% Fino Bread%"],  ["Flavor","Mix","Crumbs"],    5.0, 40.0),
        "lemon":       (["% Fresh Lemon%","% Lemon Fruit%","% Lemon Pack%","ليمون طازج%","ليمون%"],
                        ["Lemon Flavor","Lemon Juice Drink","Lemon Soda","Lemon Tea","Lemon Candy",
                         "Lemon Powder","Lemon Cake","Lemon Biscuit","Energy"],                         2.0, 40.0),
        "lemon_juice": (["% Lemon Juice%","% Squeezed Lemon%","عصير ليمون%"],
                        ["Soda","Tea","Drink","Flavored","Powder","Energy"],                             2.0, 40.0),
        "orange":      (["% Fresh Orange%","% Orange Fruit%","برتقال%"],
                        ["Orange Flavor","Orange Juice Drink","Soda","Candy","Energy"],                  2.0, 30.0),
        "pepper":      (["% Bell Pepper%","% Sweet Pepper%","% Fresh Pepper%","فلفل رومي%"],
                        ["Black Pepper","White Pepper","Chili Pepper","Pepper Sauce",
                         "Spice","Seasoning","Snack","Chips","Flavored"],                               3.0, 50.0),
        "green_pepper":(["% Green Pepper%","% Sweet Green Pepper%","فلفل أخضر%"],
                        ["Sauce","Spice","Seasoning","Snack","Flavor"],                                  3.0, 50.0),
        "bell_pepper": (["% Bell Pepper%","% Sweet Pepper%","فلفل رومي%"],
                        ["Sauce","Spice","Seasoning","Snack","Flavor"],                                  3.0, 50.0),
        "mushroom":    (["% Fresh Mushroom%","% Button Mushroom%","% Mushroom%","فطر%","مشروم%"],
                        ["Mushroom Flavor","Mushroom Soup Powder","Mushroom Sauce",
                         "Mushroom Chips","Seasoning","Energy","Supplement"],                           8.0, 80.0),
        "cucumber":    (["% Fresh Cucumber%","% Cucumber%","خيار%"],
                        ["Cucumber Flavor","Pickle","Pickled","Vinegar","Snack"],                        2.0, 30.0),
        "olive_oil":   (["% Olive Oil%","% Extra Virgin Olive Oil%","% Pure Olive Oil%","زيت زيتون%"],
                        ["Olive Oil Flavor","Dressing Mix","Marinade","Spray Flavor"],                   20.0, 200.0),
        "tomato_paste":(["% Tomato Paste%","% Tomato Puree%","% Double Concentrate%","معجون طماطم%"],
                        ["Flavor","Seasoning","Powder","Snack"],                                         3.0, 40.0),
        "tahini":      (["% Tahini%","% Sesame Paste%","طحينة%","طحينية%"],
                        ["Tahini Flavor","Snack","Dressing Mix","Powder"],                               5.0, 60.0),
        "coconut":     (["% Desiccated Coconut%","% Coconut Powder%","% Shredded Coconut%",
                         "% Coconut Flakes%","% Coconut Milk%","% Creamed Coconut%","جوز هند%"],
                        ["Coconut Flavor","Coconut Water Drink","Coconut Energy","Coconut Soda",
                         "Red Bull","Energy Drink","Vitamin Water","Protein Bar",
                         "Supplement","Candy","Biscuit","Wafer","Drink"],                               5.0, 80.0),
        "semolina":    (["% Semolina%","% Fine Semolina%","% Coarse Semolina%","سميد%"],
                        ["Semolina Flavor","Biscuit","Snack","Instant","Premix","Flavored"],             2.0, 20.0),
        "vanilla":     (["% Pure Vanilla%","% Vanilla Extract%","% Vanilla Bean%","% Vanilla Powder%","فانيليا%"],
                        ["Vanilla Flavor Drink","Vanilla Soda","Vanilla Ice Cream","Vanilla Candy",
                         "Vanilla Cake Mix","Vanilla Wafer","Vanilla Biscuit",
                         "Protein","Supplement","Energy","Drink"],                                      5.0, 80.0),
        "walnut":      (["% Walnut%","% Walnuts%","% Raw Walnut%","جوز%"],
                        ["Walnut Flavor","Walnut Cake","Walnut Biscuit","Energy","Drink"],               20.0, 150.0),
        "almond":      (["% Almond%","% Almonds%","% Raw Almond%","لوز%"],
                        ["Almond Milk","Almond Flavor","Almond Drink","Energy","Supplement"],            20.0, 150.0),
    }
    # We only backfill if every existing option is estimated.
    keys_to_backfill = [
        k for k in keyword_backfill
        if k not in all_products_map
        or all(o.get("is_estimated") for o in all_products_map.get(k, []))
    ]
    if keys_to_backfill:
        for k in keys_to_backfill:
            keywords, exclude_words, ppg_floor, ppg_ceil = keyword_backfill[k]
            try:
                include_cond = " OR ".join(
                    [f"fp.product_name LIKE :kw{i}" for i in range(len(keywords))]
                )
                # Exclude bad matches (flavored products, energy drinks, etc.)
                exclude_cond = " AND ".join(
                    [f"fp.product_name NOT LIKE :ex{j}" for j in range(len(exclude_words))]
                ) if exclude_words else "1=1"

                kw_sql = text(f"""
                    SELECT
                        fp.product_name, fp.source, fp.price,
                        fp.unit_weight_g,
                        COALESCE(n.display_name, :ing_key)  AS display_name,
                        COALESCE(n.calories_per_100g, 0)    AS calories_per_100g,
                        COALESCE(n.protein_g, 0)            AS protein_g,
                        COALESCE(n.carbs_g, 0)              AS carbs_g,
                        COALESCE(n.fats_g, 0)               AS fats_g
                    FROM fresh_products fp
                    LEFT JOIN nutrition_facts n ON n.normalized_name = :ing_key
                    WHERE fp.price > 0
                      AND fp.unit_weight_g > 0
                      AND (fp.price / fp.unit_weight_g) * 100 BETWEEN :floor AND :ceil
                      AND ({include_cond})
                      AND ({exclude_cond})
                    ORDER BY (fp.price / fp.unit_weight_g) ASC
                    LIMIT 30
                """)
                params = {{"ing_key": k, "floor": ppg_floor, "ceil": ppg_ceil}}
                for i, kw in enumerate(keywords):
                    params[f"kw{{i}}"] = kw
                for j, ex in enumerate(exclude_words):
                    params[f"ex{{j}}"] = f"%{{ex}}%"
                rows_kw = (await db.execute(kw_sql, params)).fetchall()
            except Exception as e:
                logger.debug("Keyword backfill failed for %s: %s", k, e)
                continue

            real_entries = []
            for rr in rows_kw:
                price = float(rr.price)
                db_weight = float(rr.unit_weight_g or 0)

                # ── Python-side exclude filter (double protection) ────────────
                pname_lower = (rr.product_name or "").lower()
                if any(ex.lower() in pname_lower for ex in exclude_words):
                    logger.debug("Backfill excluded '%s' for '%s'", rr.product_name, k)
                    continue

                # ── Weight recovery ──────────────────────────────────────────
                weight = _parse_weight_from_name(rr.product_name, k, db_weight)
                if price <= 0 or weight <= 0:
                    continue
                ppg = (price / weight) * 100.0
                real_entries.append({
                    "price_per_100g": ppg,
                    "display_name":   rr.display_name or k.replace("_"," ").title(),
                    "product_name":   rr.product_name,
                    "source":         rr.source,
                    "price_egp":      price,
                    "unit_weight_g":  weight,
                    "calories":       float(rr.calories_per_100g or 0),
                    "protein":        float(rr.protein_g or 0),
                    "carbs":          float(rr.carbs_g or 0),
                    "fats":           float(rr.fats_g or 0),
                    "is_estimated":   False,
                    "is_primary":     True,
                })
            if real_entries:
                # Replace any existing all-estimated pool with real products,
                # but keep the original estimated entry as a fallback at the end.
                est_kept = all_products_map.get(k, [])
                all_products_map[k] = real_entries + est_kept
                logger.info("Backfilled %d real products for '%s'", len(real_entries), k)

        # Apply is_primary filter with explicit fallback
        # (rabbit, pigeon, etc. may have no primary mapping — keep all in that case)
        for k in all_products_map:
            primary_rows = [o for o in all_products_map[k] if o.get("is_primary", True)]
            all_products_map[k] = primary_rows if primary_rows else all_products_map[k]

        # Sort each ingredient pool: non-Estimated first, then by price ASC
        for k in all_products_map:
            all_products_map[k].sort(key=lambda o: (
                1 if o.get("is_estimated") else 0,   # real products first
                o.get("price_per_100g", 0)            # then cheapest
            ))

        # ✅ Save to cache — only after full build, never when using cached version
        _cache.save_products(all_products_map, list(all_products_map.keys()), None)
        logger.info("📦 Product map cached (%d ingredients)", len(all_products_map))

    # Pack-size filter — local copy only, never mutate the cached dict
    filtered_map = {}
    for k, opts in all_products_map.items():
        small = [o for o in opts if o.get("unit_weight_g", 0) <= 2000]
        filtered_map[k] = small if small else opts  # fallback: keep large if no small

    results = []
    score_map = {i: s for s, i in scores}
    budget_for_opt = float(budget_egp) if budget_egp else None

    for idx in top_indices:
        if len(results) >= top_k * 2:
            break
        r = rows[idx]
        try:
            ingredients = json.loads(r.ingredients_json)
        except Exception:
            continue

        # ─── MILP-based product + weight selection ──────────────────────────
        opt = optimize_recipe(
            ingredients=ingredients,
            products_map=filtered_map,
            budget=budget_for_opt,
        )
        if opt["status"] != "optimal" or not opt["selected"]:
            continue

        cost  = float(opt["total_cost"])
        cal   = float(opt["total_calories"])
        prot  = float(opt["total_protein"])
        carbs = float(opt["total_carbs"])
        fats  = float(opt["total_fats"])

        # Build the per-ingredient list — matched first, then any unmatched
        # ingredients (shown for completeness with cost=0).
        ing_list: list[dict] = list(opt["selected"])
        total_w = sum(float(s.get("weight_g", 0)) for s in opt["selected"])
        selected_keys = {s["name"] for s in opt["selected"]}

        for ing in ingredients:
            key = ing.get("name", "")
            if key in selected_keys:
                continue
            wg = float(ing.get("weight_g", 0) or 0)
            total_w += wg
            ing_list.append({
                "name":         key,
                "display_name": key.replace("_", " ").title(),
                "weight_g":     wg,
                "cost_egp":     0,
                "calories":     0,
                "protein_g":    0,
            })

        if cost <= 0:
            continue

        # Per-serving
        meal_type = r.meal_type or "غداء"
        limits = {"فطار": 400, "غداء": 600, "عشاء": 500}
        limit  = limits.get(meal_type, 500)
        servings = max(1, round(total_w / limit))
        div = float(servings)

        results.append({
            "recipe_id":       r.recipe_id,
            "recipe_name":     r.recipe_name,
            "meal_type":       meal_type,
            "prep_time":       r.prep_time or 0,
            "servings":        int(div),
            "instructions":    getattr(r, "instructions", None) or "",
            "cost_egp":        round(cost  / div, 2),
            "calories":        round(cal   / div, 1),
            "protein_g":       round(prot  / div, 2),
            "carbs_g":         round(carbs / div, 2),
            "fats_g":          round(fats  / div, 2),
            "similarity":      round(score_map.get(idx, 0.5), 3),
            "budget_exceeded": bool(opt.get("budget_exceeded", False)),
            "ingredients": [
                {
                    **i,
                    # Scale per-serving amounts
                    "weight_g":         round(i["weight_g"]         / div, 1),
                    "weight_g_target":  round(i.get("weight_g_target", i["weight_g"]) / div, 1),
                    "cost_egp":         round(i["cost_egp"]         / div, 2),
                    "calories":         round(i["calories"]         / div, 1),
                    "protein_g":        round(i["protein_g"]        / div, 2),
                    # Pack info stays fixed (not scaled — it's the full product).
                    # pack_servings was already computed against the recipe's
                    # original weight_g; re-dividing here would double-count `div`.
                    "pack_price_egp": i.get("pack_price_egp", 0),
                    "pack_weight_g":  i.get("pack_weight_g",  0),
                    "pack_servings":  i.get("pack_servings",  0),
                    # Unit annotation: e.g. "150g eggs" → "≈ 3 بيضات"
                    "unit_info":      annotate_unit(
                                          i.get("name", ""),
                                          i["weight_g"] / div,
                                      ),
                }
                for i in ing_list
            ],
        })

    # Filter low similarity results (< 0.60 not relevant)
    # Separate keyword matches (tier 1-3, sim≥0.80) from semantic-only (tier 4, ≤0.55)
    keyword_matches = [r for r in results if r["similarity"] >= 0.80]
    semantic_only   = [r for r in results if 0.56 <= r["similarity"] < 0.80]

    if len(keyword_matches) >= 2:
        results = keyword_matches                      # ≥2 good matches — show only these
    elif len(keyword_matches) == 1:
        results = keyword_matches + semantic_only[:2]  # 1 match — pad with 2 semantic
    else:
        results = (semantic_only + [r for r in results if r["similarity"] >= 0.50])[:top_k]

    # Add coverage warning if >30% ingredients missing
    for r in results:
        priced = sum(1 for i in r["ingredients"] if i["cost_egp"] > 0)
        total  = len(r["ingredients"])
        r["coverage_pct"] = round(priced / total * 100) if total else 0
        r["price_complete"] = r["coverage_pct"] >= 70

    # ── Smart sort: budget-aware ─────────────────────────────────────────────
    # If user gave a budget → sort by "closest to budget" (maximize value)
    # Otherwise            → sort by semantic similarity (best match)
    if budget_egp:
        budget = float(budget_egp)
        for r in results:
            cost = r.get("cost_egp", 0) or 0
            # Score: semantic match × budget utilization (prefer meals that use more of budget)
            utilization = min(cost / budget, 1.0) if budget > 0 else 0
            r["_sort_score"] = r["similarity"] * 0.5 + utilization * 0.5
        results.sort(key=lambda x: x["_sort_score"], reverse=True)
        # Label budget utilization for frontend
        for r in results:
            cost = r.get("cost_egp", 0) or 0
            r["budget_utilization_pct"] = round(cost / budget * 100) if budget > 0 else 0
    else:
        results.sort(key=lambda x: x["similarity"], reverse=True)

    return results[:top_k]


async def _suggest_protein_alternatives(
    current_protein: float,
    target_protein: float,
    budget: float,
    db,
    top_k: int = 3,
) -> list[dict]:
    """
    When a meal doesn't meet protein target, suggest high-protein alternatives
    or add-ons from the ingredient_product_map.

    Strategy:
      - Find ingredients with high protein_per_100g
      - Sort by protein/price ratio (best value for protein)
      - Return top-k suggestions
    """
    from sqlalchemy import text

    gap = round(target_protein - current_protein, 1)
    if gap <= 0:
        return []

    # Fix for MySQL only_full_group_by: use subquery for MIN price
    sql = text("""
        SELECT
            m.ingredient_key,
            MIN(m.price_per_100g) AS min_price_per_100g,
            n.display_name,
            n.protein_g,
            n.calories_per_100g,
            n.carbs_g,
            n.fats_g
        FROM ingredient_product_map m
        JOIN nutrition_facts n ON n.normalized_name = m.ingredient_key
        WHERE m.price_per_100g > 0
          AND n.protein_g >= 15
        GROUP BY
            m.ingredient_key,
            n.display_name,
            n.protein_g,
            n.calories_per_100g,
            n.carbs_g,
            n.fats_g
        ORDER BY (n.protein_g / MIN(m.price_per_100g)) DESC
        LIMIT 20
    """)
    rows = (await db.execute(sql)).fetchall()

    # High-protein food categories for labeling
    PROTEIN_CATEGORY = {
        "chicken_breast": "🍗 Poultry",
        "chicken":        "🍗 Poultry",
        "ground_beef":    "🥩 Meat",
        "beef":           "🥩 Meat",
        "lamb":           "🥩 Meat",
        "tuna_canned":    "🐟 Fish",
        "salmon":         "🐟 Fish",
        "tilapia":        "🐟 Fish",
        "egg":            "🥚 Dairy",
        "white_cheese":   "🧀 Dairy",
        "mozzarella":     "🧀 Dairy",
        "yogurt":         "🥛 Dairy",
        "lentils":        "🫘 Legumes",
        "red_lentils":    "🫘 Legumes",
        "chickpeas":      "🫘 Legumes",
        "fava_beans":     "🫘 Legumes",
    }

    suggestions = []
    for r in rows:
        key        = r.ingredient_key
        p100       = float(r.min_price_per_100g)
        prot_100g  = float(r.protein_g)

        # How many grams needed to cover the protein gap
        grams_needed = round(gap / (prot_100g / 100), 0)
        cost_needed  = round(p100 / 100 * grams_needed, 2)
        protein_value = round(prot_100g / p100, 2)   # g protein per EGP

        # Skip if too expensive for the remaining budget
        if budget and cost_needed > budget * 0.4:
            continue

        suggestions.append({
            "ingredient_key": key,
            "display_name":   r.display_name or key.replace("_", " ").title(),
            "category":       PROTEIN_CATEGORY.get(key, "🥗 Other"),
            "protein_per_100g":  prot_100g,
            "price_per_100g":    p100,
            "protein_per_egp":   protein_value,
            "grams_to_add":      grams_needed,
            "cost_to_add_egp":   cost_needed,
            "protein_added_g":   round(gap, 1),
            "note": f"Add {grams_needed:.0f}g to get +{gap:.0f}g protein for {cost_needed:.1f} EGP",
        })

    # Sort by protein/EGP value (best deal first)
    suggestions.sort(key=lambda x: x["protein_per_egp"], reverse=True)
    return suggestions[:top_k]