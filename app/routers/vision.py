from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.vision import MealAnalysisResponse
from app.services.auth import get_current_user
from app.services.food_classifier import analyze_meal_image
from app.models.user import User

router = APIRouter(prefix="/vision", tags=["Vision AI"])

ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
MAX_SIZE      = 10 * 1024 * 1024


@router.post("/analyze-meal", response_model=MealAnalysisResponse)
async def analyze_meal(
    file: UploadFile = File(...),
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """
    Analyze a meal photo using YOLOv8 Vision AI.
    Returns meal name, macros, cost, top-3 predictions,
    macro fit score, personalization advice, and budget warnings.
    """
    content_type = (file.content_type or "image/jpeg").lower()
    if content_type not in ALLOWED_TYPES and not (file.filename or "").lower().endswith(
        (".jpg", ".jpeg", ".png", ".webp")
    ):
        raise HTTPException(status_code=415, detail=f"Unsupported file type.")

    image_bytes = await file.read()
    if len(image_bytes) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="Image exceeds 10MB limit.")
    if len(image_bytes) < 100:
        raise HTTPException(status_code=400, detail="Image file appears empty or corrupt.")

    try:
        # Pass user so the classifier can compute macro_fit + personalization
        return await analyze_meal_image(image_bytes, content_type, db, user=user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Vision API error: {str(e)}")


# ── Active Learning: User Correction ────────────────────────────────────────
class CorrectionRequest(BaseModel):
    predicted_class:  str
    correct_class:    str
    image_base64:     str   # base64 encoded image
    confidence:       float = 0.0


@router.post("/correct")
async def correct_prediction(
    req:  CorrectionRequest,
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """
    Active Learning Loop: when user corrects a wrong prediction,
    save the correction to needs_retraining table for future model improvement.
    """
    await db.execute(text("""
        INSERT INTO needs_retraining
            (user_id, predicted_class, correct_class, confidence, image_base64, created_at)
        VALUES
            (:uid, :pred, :correct, :conf, :img, NOW())
    """), {
        "uid":     user.id,
        "pred":    req.predicted_class,
        "correct": req.correct_class,
        "conf":    req.confidence,
        "img":     req.image_base64[:500],  # store thumbnail only
    })
    await db.commit()
    return {
        "status": "saved",
        "message": f"Correction saved: {req.predicted_class} → {req.correct_class}. "
                   f"This will improve future predictions."
    }


# ── GET /vision/corrections/stats ────────────────────────────────────────────
@router.get("/corrections/stats")
async def correction_stats(
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """Active Learning statistics for GP demo."""
    total      = (await db.execute(text("SELECT COUNT(*) FROM needs_retraining"))).scalar() or 0
    user_total = (await db.execute(text("SELECT COUNT(*) FROM needs_retraining WHERE user_id = :uid"), {"uid": user.id})).scalar() or 0

    top = (await db.execute(text("""
        SELECT predicted_class, correct_class, COUNT(*) as cnt
        FROM needs_retraining
        GROUP BY predicted_class, correct_class
        ORDER BY cnt DESC LIMIT 10
    """))).fetchall()

    boosted = (await db.execute(text("""
        SELECT predicted_class, correct_class, COUNT(*) as cnt
        FROM needs_retraining
        GROUP BY predicted_class, correct_class
        HAVING cnt >= 5 ORDER BY cnt DESC
    """))).fetchall()

    timeline = (await db.execute(text("""
        SELECT DATE(created_at) as day, COUNT(*) as cnt
        FROM needs_retraining
        WHERE created_at >= NOW() - INTERVAL 30 DAY
        GROUP BY DATE(created_at) ORDER BY day ASC
    """))).fetchall()

    return {
        "total_corrections": total,
        "user_corrections":  user_total,
        "top_corrections":   [{"from": r.predicted_class, "to": r.correct_class, "count": r.cnt} for r in top],
        "boosted_classes":   [{"from": r.predicted_class, "to": r.correct_class, "count": r.cnt} for r in boosted],
        "timeline":          [{"date": str(r.day), "count": r.cnt} for r in timeline],
        "model_version":     "YOLOv8s + Active Learning",
        "learning_status":   "active" if total > 0 else "collecting",
    }


# ── GET /vision/corrections/boost ────────────────────────────────────────────
@router.get("/corrections/boost")
async def get_correction_boost(
    predicted_class: str,
    db: AsyncSession = Depends(get_db),
):
    """Returns boosted class if 5+ corrections exist for this prediction."""
    result = (await db.execute(text("""
        SELECT correct_class, COUNT(*) as cnt
        FROM needs_retraining
        WHERE predicted_class = :pred
        GROUP BY correct_class HAVING cnt >= 5
        ORDER BY cnt DESC LIMIT 1
    """), {"pred": predicted_class})).fetchone()

    if result:
        return {"boosted": True, "correct_class": result.correct_class, "corrections": result.cnt}
    return {"boosted": False}
