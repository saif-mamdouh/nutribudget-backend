from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.routers import auth, users, products, matching, optimizer, personalize, vision
from app.routers import recipes, admin   # ← NEW
from app.routers import profile_pipeline  # ← Layer 1+2
from app.routers import personalize          # ← Personalization
from app.routers import chat                 # ← AI Chat with history
from app.routers import feedback             # ← User feedback / app rating

# Register ALL models before create_all
from app.models import user, product, nutrition, mapping, meal_plan  # noqa: F401
from app.models import recipe, ingredient_map                         # ← NEW

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nutribudget")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 NutriBudget API starting up...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables verified.")
    yield
    logger.info("🛑 Shutting down.")
    await engine.dispose()


app = FastAPI(
    title="NutriBudget EG API",
    version=settings.APP_VERSION,
    description="Cost-optimised, nutritionally balanced meal plans for Egypt.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://nutribudget-frontend.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_V1 = "/api/v1"

app.include_router(auth.router,             prefix=API_V1)
app.include_router(users.router,            prefix=API_V1)
app.include_router(products.router,         prefix=API_V1)
app.include_router(matching.router,         prefix=API_V1)
app.include_router(optimizer.router,        prefix=API_V1)
app.include_router(personalize.router,      prefix=API_V1)
app.include_router(vision.router,           prefix=API_V1)
app.include_router(recipes.router,          prefix=API_V1)
app.include_router(admin.router,            prefix=API_V1)
app.include_router(profile_pipeline.router, prefix=API_V1)
app.include_router(chat.router,             prefix=API_V1)
app.include_router(feedback.router,         prefix=API_V1)


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION, "env": settings.APP_ENV}
