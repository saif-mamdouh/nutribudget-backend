from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "mysql+aiomysql://root:2474@localhost:3306/nutribudget?charset=utf8mb4"

    # ── JWT ───────────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production-use-32-chars-min"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_VERSION: str = "1.0.0"

    # ── AI APIs ───────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY:   str = ""   # Get free key at https://console.groq.com

    # ── Password Reset ────────────────────────────────────────────────────────
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30

    # ── Email (Gmail SMTP) ────────────────────────────────────────────────────
    MAIL_USERNAME:  str = ""
    MAIL_PASSWORD:  str = ""
    MAIL_FROM:      str = ""
    MAIL_FROM_NAME: str = "NutriBudget EG"
    MAIL_SERVER:    str = "smtp.gmail.com"
    MAIL_PORT:      int = 587

    # ── Frontend URL (for reset links) ────────────────────────────────────────
    FRONTEND_URL:   str = "http://localhost:5173"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Cached settings — loaded once per process lifecycle."""
    return Settings()


settings = get_settings()