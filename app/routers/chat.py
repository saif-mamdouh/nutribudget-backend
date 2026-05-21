"""
app/routers/chat.py
═══════════════════
AI Nutrition Chatbot — Groq (Llama 3.3 70B) + DB chat history.

Endpoints:
  POST   /api/v1/chat          — send message, saves to DB, returns reply
  GET    /api/v1/chat/history  — load last 50 messages
  DELETE /api/v1/chat/history  — clear history

Free limits: 14,400 req/day — plenty for GP.
"""

import os
import logging
import httpx

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth import get_current_user
from app.models.user import User
from app.config import settings

log    = logging.getLogger("nutribudget.chat")
router = APIRouter(prefix="/chat", tags=["Chat AI"])

GROQ_URL    = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL  = "llama-3.3-70b-versatile"
MAX_TOKENS  = 600
HISTORY_CTX = 10   # messages sent as context to Groq
HISTORY_MAX = 50   # messages kept per user in DB


# ── Schemas ───────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str


class ChatMessageOut(BaseModel):
    role:       str
    content:    str
    created_at: str = ""


# ── System prompt ─────────────────────────────────────────────────────────────
def build_system_prompt(user: User) -> str:
    goal_map = {
        "weight_loss": "lose weight and reduce body fat",
        "muscle_gain": "build muscle and increase protein intake",
        "maintenance": "maintain current weight and stay balanced",
    }
    goal_str = goal_map.get(user.goal or "", "eat healthy on a budget")

    return f"""You are NutriBot, the AI nutrition assistant for NutriBudget Egypt.

User profile:
- Name: {user.full_name or 'User'}
- Goal: {goal_str}
- Daily calories: {user.daily_calories or 'not set'} kcal
- Daily protein:  {user.daily_protein_g or 'not set'} g
- Daily carbs:    {user.daily_carbs_g or 'not set'} g
- Daily fats:     {user.daily_fats_g or 'not set'} g
- Daily budget:   {getattr(user, 'daily_budget_egp', None) or 'not set'} EGP
- Allergies:      {getattr(user, 'allergies', None) or getattr(user, 'forbidden_foods', None) or 'none'}

Your responsibilities:
1. Answer questions about nutrition, calories, macros, and healthy eating.
2. Suggest affordable Egyptian meals that fit the user's goal and budget.
3. Explain how foods affect health in simple, practical terms.
4. Help the user understand their macro targets and how to hit them daily.
5. Reference Egyptian supermarkets (Carrefour, Hyperone, Spinneys) when relevant.

Language rules:
- Arabic input → respond in Arabic.
- English input → respond in English.
- Be warm, concise, and practical. Max 3 short paragraphs.

Boundaries:
- Only answer about food, nutrition, health, and budgeting meals.
- For medical diagnoses, recommend consulting a doctor.
- Politely decline off-topic questions.

Egyptian context:
- Prices in EGP. Typical daily budget: 30–150 EGP.
- Common staples: فول، عدس، أرز، مكرونة، بيض، خضار، فراخ.
- Molokhia, foul medames, koshari, grilled chicken = excellent budget meals."""


# ── POST /chat ────────────────────────────────────────────────────────────────
@router.post("")
async def chat(
    req:  ChatRequest,
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    groq_key = getattr(settings, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return {"reply": "⚠️ GROQ_API_KEY not set. Get your free key at https://console.groq.com"}

    # Load last N messages for context
    history_rows = (await db.execute(text("""
        SELECT role, content FROM chat_history
        WHERE user_id = :uid
        ORDER BY created_at DESC
        LIMIT :n
    """), {"uid": user.id, "n": HISTORY_CTX})).fetchall()

    context = [{"role": r.role, "content": r.content} for r in reversed(history_rows)]

    messages = [
        {"role": "system", "content": build_system_prompt(user)},
        *context,
        {"role": "user", "content": req.message},
    ]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       GROQ_MODEL,
                    "messages":    messages,
                    "max_tokens":  MAX_TOKENS,
                    "temperature": 0.7,
                },
            )
        data = response.json()

        if response.status_code != 200:
            err = data.get("error", {}).get("message", str(data)[:200])
            log.error("Groq error: %s", err)
            return {"reply": f"❌ API error: {err}"}

        reply = data["choices"][0]["message"]["content"]

    except httpx.TimeoutException:
        return {"reply": "⏱️ Response took too long. Please try again."}
    except Exception as e:
        return {"reply": f"❌ Error: {str(e)[:100]}"}

    # Save user message + reply to DB
    await db.execute(text("""
        INSERT INTO chat_history (user_id, role, content)
        VALUES (:uid, 'user', :content)
    """), {"uid": user.id, "content": req.message})

    await db.execute(text("""
        INSERT INTO chat_history (user_id, role, content)
        VALUES (:uid, 'assistant', :content)
    """), {"uid": user.id, "content": reply})

    # Prune: keep only last HISTORY_MAX messages
    await db.execute(text("""
        DELETE FROM chat_history
        WHERE user_id = :uid
          AND id NOT IN (
            SELECT id FROM (
              SELECT id FROM chat_history
              WHERE user_id = :uid
              ORDER BY created_at DESC
              LIMIT :keep
            ) AS sub
          )
    """), {"uid": user.id, "keep": HISTORY_MAX})

    await db.commit()

    return {
        "reply": reply,
        "model": GROQ_MODEL,
    }


# ── GET /chat/history ─────────────────────────────────────────────────────────
@router.get("/history")
async def get_history(
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    rows = (await db.execute(text("""
        SELECT role, content, created_at
        FROM chat_history
        WHERE user_id = :uid
        ORDER BY created_at ASC
        LIMIT :n
    """), {"uid": user.id, "n": HISTORY_MAX})).fetchall()

    return {
        "messages": [
            {
                "role":       r.role,
                "content":    r.content,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    }


# ── DELETE /chat/history ──────────────────────────────────────────────────────
@router.delete("/history", status_code=204)
async def clear_history(
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    await db.execute(
        text("DELETE FROM chat_history WHERE user_id = :uid"),
        {"uid": user.id}
    )
    await db.commit()
