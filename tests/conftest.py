import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.main import app

TEST_DATABASE_URL = settings.TEST_DATABASE_URL

# Module-level engine shared across the test session
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def setup_test_db():
    """Create all tables once per test session, drop on teardown."""
    import app.models  # noqa: F401 — register all models with Base.metadata

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(setup_test_db):
    """Transactional session — rolls back after each test for isolation."""
    async with test_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest_asyncio.fixture(loop_scope="session")
async def async_client():
    """Async HTTP test client for FastAPI app (no DB bootstrap)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(loop_scope="session")
async def db_async_client(setup_test_db):
    """Async HTTP test client for tests that require DB setup."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
