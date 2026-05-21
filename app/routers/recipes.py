"""
routers/recipes.py — with Smart Search (Translation + Fuzzy + Ingredient)
"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, text, or_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.recipe import Recipe
from app.services.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/recipes", tags=["Recipes"])


# ── Translation Dictionary (EN → AR) ─────────────────────────────────────────
FOOD_TRANSLATIONS: dict[str, list[str]] = {
    # Proteins
    "chicken":        ["فراخ", "دجاج"],
    "beef":           ["لحمة", "لحم بقري"],
    "lamb":           ["ضاني", "خروف"],
    "fish":           ["سمك"],
    "shrimp":         ["جمبري"],
    "tuna":           ["تونة"],
    "liver":          ["كبدة"],
    "sausage":        ["سجق"],
    "pigeon":         ["حمام"],
    "duck":           ["بط"],
    "rabbit":         ["أرنب"],
    # Carbs
    "rice":           ["أرز"],
    "pasta":          ["مكرونة", "ماكرونة"],
    "bread":          ["خبز", "عيش"],
    "pizza":          ["بيتزا"],
    "noodle":         ["نودلز"],
    "macaroni":       ["مكرونة"],
    # Dishes
    "koshari":        ["كشري"],
    "ful":            ["فول"],
    "falafel":        ["طعمية", "فلافل"],
    "molokhia":       ["ملوخية"],
    "kofta":          ["كفتة"],
    "kebab":          ["كباب"],
    "shawarma":       ["شاورما"],
    "burger":         ["برجر"],
    "sandwich":       ["ساندوتش", "ساندويتش", "سندوتش"],
    "club":           ["كلوب"],
    "club sandwich":  ["كلوب ساندويتش", "كلوب ساندوتش", "ساندوتش كلوب"],
    "steak":          ["ستيك"],
    "sushi":          ["سوشي"],
    "taco":           ["تاكو"],
    "hot dog":        ["هوت دوج"],
    "caesar":         ["سيزار"],
    "caesar salad":   ["سيزار سالاد"],
    # Soups
    "soup":           ["شوربة"],
    "lentil":         ["عدس"],
    "lentil soup":    ["شوربة عدس"],
    # Breakfast
    "egg":            ["بيض"],
    "eggs":           ["بيض"],
    "omelette":       ["عجة"],
    "pancake":        ["بانكيك"],
    "waffle":         ["وافل"],
    "toast":          ["توست"],
    "oats":           ["شوفان"],
    # Sweets
    "cake":           ["كيك"],
    "kunafa":         ["كنافة"],
    "basbousa":       ["بسبوسة"],
    "baklava":        ["بقلاوة"],
    "om ali":         ["أم علي"],
    "umm ali":        ["أم علي"],
    "cookie":         ["كوكيز"],
    "brownie":        ["براوني"],
    "ice cream":      ["آيس كريم"],
    # Salads & Sides
    "salad":          ["سلطة"],
    "tabouleh":       ["تبولة"],
    "fattoush":       ["فتوش"],
    "hummus":         ["حمص"],
    "baba":           ["بابا"],
    "baba ghanouj":   ["بابا غنوج"],
    # Dairy
    "cheese":         ["جبنة", "جبن"],
    "milk":           ["حليب", "لبن"],
    "yogurt":         ["زبادي", "يوغرت"],
    "cream":          ["كريمة", "قشطة"],
    # Veggies
    "potato":         ["بطاطس"],
    "eggplant":       ["باذنجان", "مسقعة"],
    "okra":           ["بامية"],
    "spinach":        ["سبانخ"],
    "zucchini":       ["كوسة"],
    "mushroom":       ["فطر", "مشروم"],
    "avocado":        ["أفوكادو"],
    # Cooking styles
    "grilled":        ["مشوي", "مشوية"],
    "fried":          ["مقلي", "مقلية"],
    "stuffed":        ["محشي", "محشية"],
    "baked":          ["بالفرن"],
}


def get_arabic_alternatives(q: str) -> list[str]:
    """Return Arabic alternatives for an English query."""
    q_lower = q.lower().strip()
    results = []
    # Exact match
    if q_lower in FOOD_TRANSLATIONS:
        results.extend(FOOD_TRANSLATIONS[q_lower])
    # Partial match — word by word
    for key, values in FOOD_TRANSLATIONS.items():
        if key in q_lower or q_lower in key:
            results.extend(values)
    return list(set(results))


def is_arabic(text: str) -> bool:
    return any("\u0600" <= c <= "\u06FF" for c in text)

def normalize_arabic(text: str) -> str:
    """
    Normalize Arabic text for fuzzy matching:
    - Normalize alef variants → ا
    - Normalize ya/alef maqsura → ي
    - Normalize ta marbuta → ه
    - Remove tashkeel
    - Normalize waw variants
    """
    import re
    # Alef variants → ا
    text = re.sub(r"[أإآٱ]", "ا", text)
    # Ya / alef maqsura → ي
    text = re.sub(r"[ىئ]", "ي", text)
    # Ta marbuta → ه
    text = re.sub(r"ة", "ه", text)
    # Remove tashkeel
    text = re.sub(r"[\u064B-\u065F]", "", text)
    return text.strip()


def build_normalized_conditions(col, q_stripped: str, alternatives: list[str]):
    """
    Build ilike conditions including normalized Arabic variants.
    Handles: ساندويتش / ساندوتش / سندوتش all matching the same recipe.
    """
    conds = [col.ilike(f"%{q_stripped}%")]
    normalized_q = normalize_arabic(q_stripped)
    if normalized_q != q_stripped:
        conds.append(col.ilike(f"%{normalized_q}%"))
    for alt in alternatives:
        conds.append(col.ilike(f"%{alt}%"))
        normalized_alt = normalize_arabic(alt)
        if normalized_alt != alt:
            conds.append(col.ilike(f"%{normalized_alt}%"))
    return conds




# ── Schemas ───────────────────────────────────────────────────────────────────
class RecipeResponse(BaseModel):
    recipe_id:    int
    recipe_name:  str
    meal_type:    Optional[str]
    ingredients:  list[dict]
    instructions: Optional[str]
    prep_time:    int
    model_config = {"from_attributes": True}


class RecipeCreate(BaseModel):
    recipe_name:  str
    meal_type:    Optional[str] = None
    ingredients:  list[dict]
    instructions: Optional[str] = None
    prep_time:    int = 0


# ── GET /recipes ──────────────────────────────────────────────────────────────
@router.get("/", response_model=list[RecipeResponse])
async def list_recipes(
    meal_type: Optional[str] = Query(None),
    q:         Optional[str] = Query(None),
    limit:     int           = Query(50, ge=1, le=300),
    offset:    int           = Query(0, ge=0),
    db:        AsyncSession  = Depends(get_db),
    _:         User          = Depends(get_current_user),
):
    stmt = select(Recipe)

    if meal_type:
        stmt = stmt.where(Recipe.meal_type == meal_type)

    if q:
        q_stripped = q.strip()
        alternatives = get_arabic_alternatives(q_stripped) if not is_arabic(q_stripped) else []

        # name conditions (with normalization for Arabic spelling variants)
        name_conds = build_normalized_conditions(Recipe.recipe_name, q_stripped, alternatives)

        # ingredients_json conditions
        ing_conds = [Recipe.ingredients_json.ilike(f"%{q_stripped}%")]
        for alt in alternatives:
            ing_conds.append(Recipe.ingredients_json.ilike(f"%{alt}%"))

        stmt = stmt.where(or_(*name_conds, *ing_conds))

    stmt = stmt.order_by(Recipe.recipe_id).offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    # Fuzzy fallback — if nothing found, try word-by-word
    if not rows and q:
        words = q.strip().split()
        if len(words) > 1:
            for word in words:
                word_alts = get_arabic_alternatives(word) if not is_arabic(word) else []
                word_name_conds = build_normalized_conditions(Recipe.recipe_name, word, word_alts)
                word_ing_conds  = [Recipe.ingredients_json.ilike(f"%{word}%")]
                for alt in word_alts:
                    word_ing_conds.append(Recipe.ingredients_json.ilike(f"%{alt}%"))
                sub = select(Recipe)
                if meal_type:
                    sub = sub.where(Recipe.meal_type == meal_type)
                sub = sub.where(or_(*word_name_conds, *word_ing_conds))
                sub = sub.order_by(Recipe.recipe_id).offset(offset).limit(limit)
                rows = (await db.execute(sub)).scalars().all()
                if rows:
                    break

    result = []
    for r in rows:
        try:
            ings = json.loads(r.ingredients_json)
        except Exception:
            ings = []
        result.append(RecipeResponse(
            recipe_id=r.recipe_id, recipe_name=r.recipe_name,
            meal_type=r.meal_type, ingredients=ings,
            instructions=r.instructions, prep_time=r.prep_time or 0,
        ))
    return result


# ── GET /recipes/stats ────────────────────────────────────────────────────────
@router.get("/stats")
async def recipe_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    total   = (await db.execute(select(func.count()).select_from(Recipe))).scalar()
    by_type = (await db.execute(
        text("SELECT meal_type, COUNT(*) as cnt FROM recipes GROUP BY meal_type")
    )).fetchall()
    return {
        "total": total,
        "by_meal_type": {r.meal_type: r.cnt for r in by_type},
    }


# ── GET /recipes/{recipe_id} ──────────────────────────────────────────────────
@router.get("/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(
    recipe_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    r = (await db.execute(
        select(Recipe).where(Recipe.recipe_id == recipe_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Recipe not found")
    try:
        ings = json.loads(r.ingredients_json)
    except Exception:
        ings = []
    return RecipeResponse(
        recipe_id=r.recipe_id, recipe_name=r.recipe_name,
        meal_type=r.meal_type, ingredients=ings,
        instructions=r.instructions, prep_time=r.prep_time or 0,
    )


# ── PUT /recipes/{recipe_id} ──────────────────────────────────────────────────
class RecipeUpdate(BaseModel):
    recipe_name:  Optional[str]       = None
    meal_type:    Optional[str]       = None
    ingredients:  Optional[list[dict]] = None
    instructions: Optional[str]       = None
    prep_time:    Optional[int]       = None


@router.put("/{recipe_id}", response_model=RecipeResponse)
async def update_recipe(
    recipe_id: int,
    payload:   RecipeUpdate,
    db:        AsyncSession = Depends(get_db),
    user:      User         = Depends(get_current_user),
):
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Admin access required")
    r = (await db.execute(
        select(Recipe).where(Recipe.recipe_id == recipe_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Recipe not found")
    if payload.recipe_name  is not None: r.recipe_name  = payload.recipe_name
    if payload.meal_type    is not None: r.meal_type    = payload.meal_type
    if payload.instructions is not None: r.instructions = payload.instructions
    if payload.prep_time    is not None: r.prep_time    = payload.prep_time
    if payload.ingredients  is not None:
        r.ingredients_json = json.dumps(payload.ingredients, ensure_ascii=False)
    await db.commit()
    await db.refresh(r)
    try:
        ings = json.loads(r.ingredients_json)
    except Exception:
        ings = []
    return RecipeResponse(
        recipe_id=r.recipe_id, recipe_name=r.recipe_name,
        meal_type=r.meal_type, ingredients=ings,
        instructions=r.instructions, prep_time=r.prep_time or 0,
    )


# ── DELETE /recipes/{recipe_id} ───────────────────────────────────────────────
@router.delete("/{recipe_id}", status_code=204)
async def delete_recipe(
    recipe_id: int,
    db:        AsyncSession = Depends(get_db),
    user:      User         = Depends(get_current_user),
):
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Admin access required")
    r = (await db.execute(
        select(Recipe).where(Recipe.recipe_id == recipe_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Recipe not found")
    await db.delete(r)
    await db.commit()


# ── POST /recipes/ ────────────────────────────────────────────────────────────
@router.post("/", response_model=RecipeResponse, status_code=201)
async def add_recipe(
    payload:      RecipeCreate,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    max_id = (await db.execute(
        text("SELECT COALESCE(MAX(recipe_id),0) FROM recipes")
    )).scalar()
    new_id = max_id + 1
    recipe = Recipe(
        recipe_id=new_id,
        recipe_name=payload.recipe_name,
        meal_type=payload.meal_type,
        ingredients_json=json.dumps(payload.ingredients, ensure_ascii=False),
        instructions=payload.instructions,
        prep_time=payload.prep_time,
    )
    db.add(recipe)
    await db.flush()
    await db.refresh(recipe)
    return RecipeResponse(
        recipe_id=recipe.recipe_id, recipe_name=recipe.recipe_name,
        meal_type=recipe.meal_type, ingredients=payload.ingredients,
        instructions=recipe.instructions, prep_time=recipe.prep_time or 0,
    )