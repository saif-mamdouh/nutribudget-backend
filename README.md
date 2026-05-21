# ──────────────────────────────────────────────────────────────────────────────
# NutriBudget EG — Phase 1 Setup Guide (MySQL)
# ──────────────────────────────────────────────────────────────────────────────

## 1. Prerequisites
- Python 3.11+
- MySQL 8.0+ running locally
- Redis 7+ (for future phases)

## 2. Create virtualenv & install dependencies
```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Configure environment
```bash
cp .env.example .env
# Edit .env — set DATABASE_URL and SECRET_KEY:
#   DATABASE_URL=mysql+aiomysql://root:YOUR_PASSWORD@localhost:3306/nutribudget
#   SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

## 4. Create the database (MySQL)
```sql
CREATE DATABASE nutribudget CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 5. Run the server
```bash
uvicorn app.main:app --reload --port 8000
```
Tables are auto-created on first startup via SQLAlchemy's `create_all`.

## 6. Interactive API docs
Open http://localhost:8000/docs

## 7. Test the auth flow (curl)
```bash
# Signup
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@nutribudget.eg","password":"Test1234!","password_confirm":"Test1234!","full_name":"Ahmed"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@nutribudget.eg","password":"Test1234!"}'

# Use the access_token:
curl http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer <access_token>"
```

## 8. Alembic migrations (production)
```bash
alembic init alembic
# edit alembic/env.py — import Base from app.database, use DATABASE_URL
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

## 9. MySQL connection string format
```
mysql+aiomysql://USER:PASSWORD@HOST:PORT/DATABASE?charset=utf8mb4
```
