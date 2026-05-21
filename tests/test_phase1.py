"""
Phase 1 — Auth & User CRUD Tests
Run: python -m pytest tests/test_phase1.py -v -p no:warnings
"""
import time
import pytest
from httpx import AsyncClient


def unique_email(prefix="user"):
    """Generates a unique email per test to avoid duplicate conflicts."""
    return f"{prefix}_{int(time.time() * 1000)}@nutribudget.eg"


PASSWORD = "TestPass99!"

SIGNUP_BASE = {
    "password": PASSWORD,
    "password_confirm": PASSWORD,
    "full_name": "Ahmed",
    "daily_budget_egp": 150,
    "allergies": ["nuts"],
}


async def create_and_login(client: AsyncClient, email: str) -> str:
    """Helper: signup + login → returns access token."""
    await client.post("/api/v1/auth/signup", json={**SIGNUP_BASE, "email": email})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


# ── Signup ────────────────────────────────────────────────────────────────────
async def test_signup_success(client):
    email = unique_email("signup")
    r = await client.post("/api/v1/auth/signup", json={**SIGNUP_BASE, "email": email})
    assert r.status_code == 201
    data = r.json()
    assert data["email"] == email
    assert "hashed_password" not in data
    assert data["allergies"] == ["nuts"]


async def test_signup_duplicate(client):
    email = unique_email("dup")
    # First signup
    r1 = await client.post("/api/v1/auth/signup", json={**SIGNUP_BASE, "email": email})
    assert r1.status_code == 201
    # Duplicate — must be 409
    r2 = await client.post("/api/v1/auth/signup", json={**SIGNUP_BASE, "email": email})
    assert r2.status_code == 409


async def test_signup_password_mismatch(client):
    r = await client.post("/api/v1/auth/signup", json={
        **SIGNUP_BASE,
        "email": unique_email("mismatch"),
        "password_confirm": "WrongPass!",
    })
    assert r.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────
async def test_login_success(client):
    email = unique_email("login")
    await client.post("/api/v1/auth/signup", json={**SIGNUP_BASE, "email": email})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200
    assert "access_token" in r.json()
    assert "refresh_token" in r.json()
    assert r.json()["token_type"] == "bearer"


async def test_login_wrong_password(client):
    email = unique_email("wrongpw")
    await client.post("/api/v1/auth/signup", json={**SIGNUP_BASE, "email": email})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPass!"})
    assert r.status_code == 401


async def test_login_nonexistent_user(client):
    r = await client.post("/api/v1/auth/login", json={
        "email": "nobody@nutribudget.eg",
        "password": PASSWORD,
    })
    assert r.status_code == 401


# ── Token refresh ─────────────────────────────────────────────────────────────
async def test_refresh_token(client):
    email = unique_email("refresh")
    await client.post("/api/v1/auth/signup", json={**SIGNUP_BASE, "email": email})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    refresh_token = login.json()["refresh_token"]

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    assert "access_token" in r.json()


async def test_refresh_invalid_token(client):
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": "bad.token.here"})
    assert r.status_code == 401


# ── User CRUD ─────────────────────────────────────────────────────────────────
async def test_get_me(client):
    email = unique_email("getme")
    token = await create_and_login(client, email)
    r = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == email


async def test_update_me(client):
    email = unique_email("update")
    token = await create_and_login(client, email)
    r = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"daily_budget_egp": 250, "allergies": ["nuts", "gluten"]},
    )
    assert r.status_code == 200
    assert r.json()["daily_budget_egp"] == 250
    assert "gluten" in r.json()["allergies"]


async def test_delete_me(client):
    email = unique_email("delete")
    token = await create_and_login(client, email)
    r = await client.delete("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 204
    # Subsequent request should fail — account deactivated
    r2 = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 401


async def test_unauthorized_access(client):
    r = await client.get("/api/v1/users/me")
    assert r.status_code == 403
