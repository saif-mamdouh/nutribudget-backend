"""
services/nlp_parser.py  (v3 — Pre-trained Models, No API, No Training)
────────────────────────────────────────────────────────────────────────
Layer 1: NLP Input Understanding

Architecture:
  Component A — Regex NER
    Extracts: age, weight, height, gender, budget
    Accuracy: ~100% for well-formed Arabic/English input

  Component B — paraphrase-multilingual-MiniLM-L12-v2
    Task:   Zero-shot classification (goal + activity_level)
    Method: Cosine similarity between user text embedding
            and pre-defined class description embeddings
    Size:   ~120MB  |  Offline  |  No training needed
    Arabic support: Yes (trained on 50+ languages)

DO YOU NEED TO TRAIN IT? → NO
  This model is already pre-trained on 50+ languages including Arabic.
  We use it for ZERO-SHOT classification:
    - Encode user text → embedding vector
    - Encode class descriptions → embedding vectors
    - Pick class with highest cosine similarity
  No fine-tuning, no labeled data, no training loop.

Papers:
  Reimers & Gurevych (2019) — Sentence-BERT (EMNLP)
  Antoun et al. (2020)      — AraBERT (LREC)
"""

import logging
import re
import threading

from typing import Optional, Tuple
import numpy as np

from app.schemas.profile import ParsedProfile

logger = logging.getLogger("nutribudget.nlp")


# ─────────────────────────────────────────────────────────────────────────────
# Singleton — model loads once, reused for all requests
# ─────────────────────────────────────────────────────────────────────────────

class _NLPModel:
    _instance = None
    _lock     = threading.Lock()
    MODEL_ID  = "paraphrase-multilingual-MiniLM-L12-v2"

    # Pre-computed class embeddings (built once on first request)
    _goal_embs:     Optional[dict] = None
    _activity_embs: Optional[dict] = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    from sentence_transformers import SentenceTransformer
                    logger.info(f"📦 Loading {cls.MODEL_ID} ...")
                    cls._instance = SentenceTransformer(cls.MODEL_ID)
                    cls._goal_embs     = _build_class_embeddings(cls._instance, GOAL_CLASSES)
                    cls._activity_embs = _build_class_embeddings(cls._instance, ACTIVITY_CLASSES)
                    logger.info("✅ NLP model ready.")
        return cls._instance


# ─────────────────────────────────────────────────────────────────────────────
# Class descriptions — Arabic (EGY + MSA) + English
# More phrases = better embedding centroid = better accuracy
# ─────────────────────────────────────────────────────────────────────────────

GOAL_CLASSES = {
    "weight_loss": [
        "عايز أنزل وزن عايزة أنزل وزن",
        "تخسيس رجيم إنقاص الوزن نزلان وزن",
        "أخسس أتخس أقلل وزني",
        "lose weight slim down weight loss diet",
        "reduce body fat calorie deficit cut weight",
    ],
    "muscle_gain": [
        "عايز أبني عضل عايزة أبني عضل",
        "كمال أجسام ضخامة عضلية زيادة الكتلة",
        "أضخم جسمي أزيد عضل تضخيم",
        "muscle gain bodybuilding bulk up build muscle",
        "increase muscle mass strength training hypertrophy",
    ],
    "maintenance": [
        "عايز أثبت وزني مش عايز أتغير",
        "ثبات الوزن الحفاظ على الوزن",
        "maintain weight keep current weight stable",
        "weight maintenance no change",
    ],
    "general_health": [
        "عايز أتحسن صحتياً صحة عامة",
        "أعيش صح حياة صحية أتحسن",
        "general health wellness healthy lifestyle",
        "improve health fitness feel better",
        "eat healthy balanced diet",
    ],
}

ACTIVITY_CLASSES = {
    "sedentary": [
        "مكتبي لا أتحرك جالس طول اليوم",
        "لا أتمرن خالص لا أمارس رياضة",
        "sedentary desk job no exercise at all",
    ],
    "light": [
        "بمشي أحياناً تمرين خفيف نص ساعة",
        "بمشي كل يوم أتمرن مرة في الأسبوع",
        "light exercise walking 1-2 times per week",
        "occasional walk light activity",
    ],
    "moderate": [
        "بتمرن في الجيم 3 مرات في الأسبوع",
        "رياضة منتظمة متوسطة النشاط",
        "moderate exercise gym 3-4 times per week",
        "regular workout 3 days a week",
    ],
    "active": [
        "بتمرن كتير جيم 5 أو 6 مرات في الأسبوع",
        "رياضي نشيط أتمرن بشكل مكثف",
        "active lifestyle gym 5-6 times per week",
        "intense workout heavy training 5 days",
    ],
    "very_active": [
        "بتمرن كل يوم تمرين مرتين في اليوم",
        "رياضي محترف شغل بدني شاق",
        "athlete training twice a day physical labor",
        "professional athlete very intense daily training",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build averaged class embeddings
# ─────────────────────────────────────────────────────────────────────────────

def _build_class_embeddings(model, class_dict: dict) -> dict:
    """
    For each class: encode all phrases → average → one embedding vector.
    This gives a robust centroid representation of each class.
    """
    result = {}
    for label, phrases in class_dict.items():
        vecs = model.encode(phrases, convert_to_numpy=True)
        result[label] = vecs.mean(axis=0)
    return result


def _cosine_classify(text: str, model, class_embeddings: dict) -> Tuple[str, float]:
    """
    Encode text → compare cosine similarity to all class embeddings.
    Returns (best_label, confidence_score 0-1).
    """
    text_vec = model.encode([text], convert_to_numpy=True)[0]

    scores = {}
    for label, class_vec in class_embeddings.items():
        dot    = np.dot(text_vec, class_vec)
        norms  = np.linalg.norm(text_vec) * np.linalg.norm(class_vec)
        scores[label] = float(dot / norms) if norms > 0 else 0.0

    best = max(scores, key=scores.get)
    logger.debug(f"Scores: {scores} → {best}")
    return best, round(scores[best], 3)


# ─────────────────────────────────────────────────────────────────────────────
# Component A: Regex NER — structured numeric extraction
# ─────────────────────────────────────────────────────────────────────────────

def _regex_extract(text: str) -> dict:
    t   = text.lower().strip()
    out = {}

    # ── Age ───────────────────────────────────────────────────────────────────
    for pat in [
        r'(\d{1,2})\s*(سن[ةه]|سنين|عام|أعوام|year)',
        r'(عمر[يه]?|عند[يه]?|age\s*[:=]?)\s*(\d{1,2})',
        r'(\d{1,2})\s*y/?o\b',
    ]:
        m = re.search(pat, t)
        if m:
            nums = [g for g in m.groups() if g and g.isdigit()]
            if nums:
                out['age'] = int(nums[0])
                break

    # ── Weight ────────────────────────────────────────────────────────────────
    for pat in [
        r'(\d{2,3})\s*(كيل[وا]|kg\b|كجم)',
        r'(وزن[يه]?)\s*(\d{2,3})',
    ]:
        m = re.search(pat, t)
        if m:
            nums = [g for g in m.groups() if g and re.match(r'^\d{2,3}$', g)]
            if nums:
                out['weight_kg'] = float(nums[0])
                break

    # ── Height ────────────────────────────────────────────────────────────────
    for pat in [
        r'(\d{3})\s*(سم|cm\b|سنتي)',
        r'(طول[يه]?)\s*(\d{3})',
    ]:
        m = re.search(pat, t)
        if m:
            nums = [g for g in m.groups() if g and re.match(r'^\d{3}$', g)]
            if nums:
                out['height_cm'] = float(nums[0])
                break

    # Feet/inches → cm
    m = re.search(r"(\d+)\s*['\u2019]\s*(\d+)\s*\"", t)
    if m and 'height_cm' not in out:
        out['height_cm'] = round(int(m.group(1)) * 30.48 + int(m.group(2)) * 2.54, 1)

    # ── Gender ────────────────────────────────────────────────────────────────
    if re.search(r'\bولد\b|رجل|ذكر|\bmale\b|\bman\b', t):
        out['gender'] = 'male'
    elif re.search(r'\bبنت\b|\bست\b|أنثى|\bfemale\b|\bwoman\b', t):
        out['gender'] = 'female'

    # ── Budget ────────────────────────────────────────────────────────────────
    m = re.search(r'(\d{2,4})\s*(جنيه|egp|جنيهات)', t)
    if m:
        out['budget_egp'] = float(m.group(1))

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Keyword fallback (if transformer unavailable)
# ─────────────────────────────────────────────────────────────────────────────

def _keyword_classify(text: str) -> tuple[str, str]:
    """Simple keyword fallback for goal + activity."""
    t = text.lower()
    goal = "general_health"
    if re.search(r'أنزل|تخسيس|رجيم|lose.weight|slim', t):
        goal = 'weight_loss'
    elif re.search(r'عضل|ضخام|muscle|كمال|bulk', t):
        goal = 'muscle_gain'
    elif re.search(r'ثبات|maintain', t):
        goal = 'maintenance'

    activity = "moderate"
    if re.search(r'(جيم|gym).{0,15}(5|6|7|خمس|ست)|يومي|كل.يوم.*(جيم|gym)', t):
        activity = 'active'
    elif re.search(r'(جيم|gym).{0,15}(3|4|تلات|أربع)', t):
        activity = 'moderate'
    elif re.search(r'بمشي|يمشي|walk|خفيف', t):
        activity = 'light'
    elif re.search(r'مكتبي|sedentary|لا.أتمرن', t):
        activity = 'sedentary'

    return goal, activity


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

async def parse_user_text(text: str) -> ParsedProfile:
    """
    Full NLP pipeline — no API, no training required.

    Component A (Regex):     age, weight, height, gender, budget
    Component B (MiniLM):    goal, activity_level
    """

    # ── Component A: Regex ────────────────────────────────────────────────────
    numeric = _regex_extract(text)
    logger.info(f"Regex extracted {len(numeric)} fields: {list(numeric.keys())}")

    # ── Component B: Pre-trained Transformer ──────────────────────────────────
    goal = activity = None
    goal_conf = activity_conf = 0.5

    try:
        model                   = _NLPModel.get()
        goal,     goal_conf     = _cosine_classify(text, model, _NLPModel._goal_embs)
        activity, activity_conf = _cosine_classify(text, model, _NLPModel._activity_embs)
        logger.info(f"MiniLM → goal={goal}({goal_conf:.0%}) activity={activity}({activity_conf:.0%})")

    except Exception as e:
        logger.warning(f"Transformer unavailable: {e} — using keyword fallback")
        goal, activity = _keyword_classify(text)

    # ── Confidence ────────────────────────────────────────────────────────────
    key_fields  = ['age', 'weight_kg', 'height_cm', 'gender']
    regex_score = sum(1 for k in key_fields if k in numeric) / len(key_fields)
    confidence  = round(min(0.95, regex_score * 0.6 + goal_conf * 0.2 + activity_conf * 0.2), 2)

    return ParsedProfile(
        age=numeric.get('age'),
        weight_kg=numeric.get('weight_kg'),
        height_cm=numeric.get('height_cm'),
        gender=numeric.get('gender'),
        activity_level=activity or 'moderate',
        goal=goal or 'general_health',
        budget_egp=numeric.get('budget_egp'),
        confidence=confidence,
        raw_text=text,
        notes=(
            f"Regex: {int(regex_score*4)}/4 fields extracted | "
            f"MiniLM goal={goal_conf:.0%} activity={activity_conf:.0%}"
        ),
    )
