import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings
from database import Base, get_db
from main import app

os.environ["DB_URL"] = settings.test_db_url


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def test_engine():
    engine = create_async_engine(
        settings.test_db_url,
        poolclass=NullPool,
    )
    return engine


@pytest.fixture(scope="session")
async def setup_database(test_engine: AsyncEngine):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest.fixture
async def db_session(
    test_engine: AsyncEngine,
    setup_database,  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType, reportUnusedParameter]
):
    conn = await test_engine.connect()
    trans = await conn.begin()

    test_async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async with test_async_session() as session:
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
            await conn.close()


@pytest.fixture
async def client(db_session: AsyncSession):
    async def get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = get_db_override

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def create_test_user(
    client: AsyncClient,
    username: str = "test user",
    email: str = "testuser@example.com",
    password: str = "testpass1",
):
    response = await client.post(
        "/api/users", json={"username": username, "email": email, "password": password}
    )

    assert response.status_code == 201, f"Failed to create user: {response.text}"
    return response.json()
