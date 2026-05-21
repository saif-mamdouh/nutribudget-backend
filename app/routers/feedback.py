"""
routers/feedback.py
────────────────────
User feedback collection — app rating + comments.

Endpoints:
  POST /feedback           — submit rating + optional comment
  GET  /feedback/my        — get current user's feedback
  GET  /feedback/stats     — aggregate stats (admin only)
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth import get_current_user, get_current_admin
from app.models.user import User

router = APIRouter(prefix="/feedback", tags=["Feedback"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5, description="1-5 stars")
    notes:  Optional[str] = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    id:         int
    rating:     int
    notes:      Optional[str]
    created_at: datetime


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/", status_code=201)
async def submit_feedback(
    payload: FeedbackCreate,
    db:      AsyncSession = Depends(get_db),
    user:    User         = Depends(get_current_user),
):
    """Submit app rating + optional comment."""
    await db.execute(text("""
        INSERT INTO user_feedback (user_id, plan_id, rating, notes, created_at)
        VALUES (:uid, :plan_id, :rating, :notes, NOW())
    """), {
        "uid":     user.id,
        "plan_id": None,   # NULL = general app feedback (not tied to a plan)
        "rating":  payload.rating,
        "notes":   payload.notes,
    })
    await db.commit()
    return {"status": "ok", "message": "Thanks for your feedback!"}


@router.get("/my")
async def get_my_feedback(
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """Get current user's feedback history."""
    rows = (await db.execute(text("""
        SELECT id, rating, notes, created_at
        FROM user_feedback
        WHERE user_id = :uid
        ORDER BY created_at DESC
    """), {"uid": user.id})).fetchall()

    return {
        "feedback": [
            {
                "id":         r.id,
                "rating":     r.rating,
                "notes":      r.notes,
                "created_at": str(r.created_at),
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/stats")
async def feedback_stats(
    db:    AsyncSession = Depends(get_db),
    _user: User         = Depends(get_current_admin),
):
    """Aggregate feedback statistics — admin only."""
    row = (await db.execute(text("""
        SELECT
            COUNT(*)                    AS total,
            ROUND(AVG(rating), 2)       AS avg_rating,
            SUM(CASE WHEN rating = 5 THEN 1 ELSE 0 END) AS five_star,
            SUM(CASE WHEN rating = 4 THEN 1 ELSE 0 END) AS four_star,
            SUM(CASE WHEN rating = 3 THEN 1 ELSE 0 END) AS three_star,
            SUM(CASE WHEN rating = 2 THEN 1 ELSE 0 END) AS two_star,
            SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) AS one_star,
            SUM(CASE WHEN notes IS NOT NULL AND notes != '' THEN 1 ELSE 0 END) AS with_comments
        FROM user_feedback
    """))).fetchone()

    recent_comments = (await db.execute(text("""
        SELECT uf.rating, uf.notes, uf.created_at, u.full_name
        FROM user_feedback uf
        LEFT JOIN users u ON u.id = uf.user_id
        WHERE uf.notes IS NOT NULL AND uf.notes != ''
        ORDER BY uf.created_at DESC
        LIMIT 20
    """))).fetchall()

    return {
        "total":       row.total or 0,
        "avg_rating":  float(row.avg_rating or 0),
        "distribution": {
            "5": row.five_star  or 0,
            "4": row.four_star  or 0,
            "3": row.three_star or 0,
            "2": row.two_star   or 0,
            "1": row.one_star   or 0,
        },
        "with_comments": row.with_comments or 0,
        "recent_comments": [
            {
                "rating":     c.rating,
                "notes":      c.notes,
                "user":       c.full_name or "Anonymous",
                "created_at": str(c.created_at),
            }
            for c in recent_comments
        ],
    }