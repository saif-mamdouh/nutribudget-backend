from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base, AsyncSessionLocal
from app.routers import auth, users, products, matching, optimizer, personalize, vision
from app.routers import recipes, admin
from app.routers import profile_pipeline
from app.routers import personalize
from app.routers import chat
from app.routers import feedback

from app.models import user, product, nutrition, mapping, meal_plan  # noqa: F401
from app.models import recipe, ingredient_map

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nutribudget")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 NutriBudget API starting up...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables verified.")

    # Pre-warm MiniLM model + recipe embeddings cache
    try:
        from app.services.nlp_parser import _NLPModel
        from app.services.meal_optimizer import _load_priced_recipes
        from app.services import personalization

        logger.info("⏳ Pre-loading MiniLM model...")
        model = _NLPModel.get()
        logger.info("✅ MiniLM model loaded.")

        logger.info("⏳ Pre-computing recipe embeddings...")
        async with AsyncSessionLocal() as db:
            recipes_data = await _load_priced_recipes(db)
            if recipes_data:
                names = [r["recipe_name"] for r in recipes_data]
                personalization._RECIPE_VECS_CACHE = model.encode(names, convert_to_numpy=True)
                personalization._RECIPE_NAMES_CACHE = names
                logger.info(f"✅ Cached embeddings for {len(names)} recipes")
    except Exception as e:
        logger.warning(f"⚠️ Pre-warm skipped: {e}")

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
