import asyncio
import os
import pathlib
import tempfile

import pytest
import pytest_asyncio

TMP = tempfile.mkdtemp(prefix="shoescout-test-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TMP}/test.db"
os.environ["MOCK_MODE"] = "true"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["ADMIN_PASSWORD"] = "test-password-123"
os.environ["CREDENTIALS_ENCRYPTION_KEY_B64"] = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="  # test-only 32 bytes
os.environ["ADMIN_AUTH_SECRET"] = "test-auth-secret"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ELEVENLABS_API_KEY", None)

from app.config import get_settings  # noqa: E402
get_settings.cache_clear()

from app.db import get_sessionmaker, init_db  # noqa: E402
from app.search.index import InMemorySearchBackend, set_search_backend  # noqa: E402
from app.seed.seed import seed_demo  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def seeded():
    await init_db()
    async with get_sessionmaker()() as db:
        await seed_demo(db)
        backend = InMemorySearchBackend()
        await backend.rebuild(db)
        set_search_backend(backend)
    yield True


@pytest_asyncio.fixture
async def db(seeded):
    async with get_sessionmaker()() as session:
        yield session


@pytest_asyncio.fixture
async def client(seeded):
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
