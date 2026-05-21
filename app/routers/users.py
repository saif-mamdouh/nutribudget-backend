import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate
from app.services.auth import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])


# ── GET /me ───────────────────────────────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's full profile."""
    return current_user


# ── PATCH /me ─────────────────────────────────────────────────────────────────
@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Partial update — only provided fields are changed."""
    update_data = payload.model_dump(exclude_unset=True)

    # Serialise list fields → JSON string for MySQL TEXT storage
    for list_field in ("allergies", "forbidden_foods"):
        if list_field in update_data and isinstance(update_data[list_field], list):
            update_data[list_field] = json.dumps(update_data[list_field], ensure_ascii=False)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.add(current_user)
    await db.flush()
    await db.refresh(current_user)
    return current_user


# ── DELETE /me ────────────────────────────────────────────────────────────────
@router.delete("/me", status_code=204)
async def delete_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete: deactivates the account rather than erasing data."""
    current_user.is_active = False
    db.add(current_user)


# ── GET /{user_id}  (internal / admin use) ────────────────────────────────────
@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),   # must be authenticated
):
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# ── GET /me/today — today's actual macros from meal plans ────────────────────
@router.get("/me/today")
async def get_today_macros(
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """Returns today's actual calories/macros from meal plans created today."""
    from sqlalchemy import text
    from datetime import date

    rows = (await db.execute(text("""
        SELECT total_calories, total_protein_g, total_carbs_g, total_fats_g,
               total_cost_egp, period
        FROM meal_plans
        WHERE user_id = :uid
          AND DATE(created_at) = CURDATE()
        ORDER BY created_at DESC
    """), {"uid": user.id})).fetchall()

    if not rows:
        return {"calories": 0, "protein_g": 0,
                "carbs_g": 0, "fats_g": 0, "cost_egp": 0, "plans_today": 0}

    # Primary source: meal_logs (actual logged meals today)
    log_rows = (await db.execute(text("""
        SELECT SUM(calories) AS cal, SUM(protein_g) AS prot,
               SUM(carbs_g) AS carb, SUM(fats_g) AS fat,
               SUM(cost_egp) AS cost, COUNT(*) AS cnt
        FROM meal_logs
        WHERE user_id = :uid AND DATE(logged_at) = CURDATE()
    """), {"uid": user.id})).fetchone()

    if log_rows and log_rows.cnt and log_rows.cnt > 0:
        return {
            "calories":    round(float(log_rows.cal   or 0), 1),
            "protein_g":   round(float(log_rows.prot  or 0), 2),
            "carbs_g":     round(float(log_rows.carb  or 0), 2),
            "fats_g":      round(float(log_rows.fat   or 0), 2),
            "cost_egp":    round(float(log_rows.cost  or 0), 2),
            "plans_today": int(log_rows.cnt),
            "source":      "logged",
        }

    # Fallback: latest meal_plan from today
    chosen   = rows[0]   # most recent plan
    divisor  = 7 if (chosen.period or '').lower() == 'weekly' else 1

    # For weekly plans, try to get today's specific day meals
    today_meals = []
    if (chosen.period or '').lower() == 'weekly':
        from datetime import date as _date
        weekly_row = (await db.execute(text("""
            SELECT meals_json, created_at FROM meal_plans
            WHERE user_id = :uid AND period = 'weekly' AND meals_json IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
        """), {"uid": user.id})).fetchone()

        if weekly_row and weekly_row.meals_json:
            import json as _json
            all_meals = _json.loads(weekly_row.meals_json)
            created = weekly_row.created_at.date() if weekly_row.created_at else _date.today()
            day_num = (_date.today() - created).days + 1
            today_meals = [m for m in all_meals if m.get("day") == day_num]

            if today_meals:
                # Use actual today's day meals instead of total/7
                return {
                    "calories":    round(sum(m.get("calories", 0) for m in today_meals), 1),
                    "protein_g":   round(sum(m.get("protein_g", 0) for m in today_meals), 2),
                    "carbs_g":     round(sum(m.get("carbs_g", 0) for m in today_meals), 2),
                    "fats_g":      round(sum(m.get("fats_g", 0) for m in today_meals), 2),
                    "cost_egp":    round(sum(m.get("cost_egp", 0) for m in today_meals), 2),
                    "plans_today": len(rows),
                    "today_meals": today_meals,
                }

    return {
        "calories":    round(float(chosen.total_calories   or 0) / divisor, 1),
        "protein_g":   round(float(chosen.total_protein_g  or 0) / divisor, 2),
        "carbs_g":     round(float(chosen.total_carbs_g    or 0) / divisor, 2),
        "fats_g":      round(float(chosen.total_fats_g     or 0) / divisor, 2),
        "cost_egp":    round(float(chosen.total_cost_egp   or 0) / divisor, 2),
        "plans_today": len(rows),
    }


# ── GET /me/streak ────────────────────────────────────────────────────────────
@router.get("/me/streak")
async def get_streak(
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    from sqlalchemy import text
    from datetime import date, timedelta

    rows = (await db.execute(text("""
        SELECT DATE(created_at) AS plan_date
        FROM meal_plans
        WHERE user_id = :uid
        GROUP BY DATE(created_at)
        ORDER BY plan_date DESC
    """), {"uid": user.id})).fetchall()

    if not rows:
        return {"streak": 0, "message": "Start your journey today!"}

    active_days = {r.plan_date for r in rows}
    today       = date.today()
    yesterday   = today - timedelta(days=1)

    if today not in active_days and yesterday not in active_days:
        return {"streak": 0, "message": "Start a new streak today!"}

    streak = 0
    check  = today if today in active_days else yesterday
    while check in active_days:
        streak += 1
        check  -= timedelta(days=1)

    label = (
        "🔥 On fire!"         if streak >= 30 else
        "💪 Keep it up!"      if streak >= 14 else
        "⭐ Great streak!"    if streak >= 7  else
        "✨ Building habits!" if streak >= 3  else
        "Keep nourishing yourself"
    )
    return {"streak": streak, "message": label}
