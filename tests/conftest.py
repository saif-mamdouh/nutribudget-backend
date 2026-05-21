"""
conftest.py — Python 3.9 + Windows + aiomysql definitive fix
─────────────────────────────────────────────────────────────
ROOT CAUSE:
  aiomysql connections bind to the event loop that created them.
  On Python 3.9, the ProactorEventLoop on Windows is strict about this.
  Any engine created at module-import time binds its pool to the
  "default" loop — which is DIFFERENT from the loop pytest-asyncio
  creates for the test session.

THE FIX: NullPool
  NullPool disables connection pooling entirely.
  Every DB operation opens a fresh connection and closes it immediately.
  No connections are cached between event loops → no "Future attached
  to a different loop" errors. Slight perf hit in tests is acceptable.
"""

import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import Base, get_db
from app.main import app

# ── Test DB URL ───────────────────────────────────────────────────────────────
_db_name = settings.DATABASE_URL.rsplit("/", 1)[-1].split("?")[0]
TEST_DB_URL = settings.DATABASE_URL.replace(f"/{_db_name}", "/nutribudget_test")

# ── Engine with NullPool — CRITICAL for Python 3.9 + aiomysql ─────────────────
# NullPool = no connection reuse across coroutines/loops.
# Every request: open connection → execute → close. Zero loop-binding issues.
test_engine = create_async_engine(
    TEST_DB_URL,
    poolclass=NullPool,   # ← THE FIX
    echo=False,
)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    expire_on_commit=False,
)


# ── DB dependency override ────────────────────────────────────────────────────
async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


# ── Session-scoped event loop (keeps all tests in ONE loop) ───────────────────
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ── DB setup / teardown ───────────────────────────────────────────────────────
@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Graceful teardown — ignore errors if loop is already closing
    try:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    except Exception:
        pass


# ── HTTP client ───────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── Pre-authenticated client ──────────────────────────────────────────────────
@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    """Unique user per test → no duplicate-email conflicts."""
    import time
    email = f"auto_{int(time.time() * 1000)}@nutribudget.eg"
    await client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": "TestPass99!",
        "password_confirm": "TestPass99!",
        "full_name": "Auto User",
    })
    r = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "TestPass99!",
    })
    client.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return client