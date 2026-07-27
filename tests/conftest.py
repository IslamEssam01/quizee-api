import os

from pydantic import validate_email

os.environ["ENV"] = "TEST"
from config import settings

settings.db_url = settings.test_db_url

import pytest
from httpx import ASGITransport, AsyncClient
from hypothesis import HealthCheck, given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st
from sqlalchemy import NullPool
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import models
from database import Base, get_db
from main import app


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
        bind=conn,
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


async def login_user(
    client: AsyncClient,
    email: str = "testuser@example.com",
    password: str = "testpass1",
    client_type: str = "web",
):
    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-Client-Type": client_type},
    )

    assert response.status_code == 200, f"Failed to login user: {response.text}"
    return response.json()["access_token"], response.json()["refresh_token"]


def auth_header(token: str):
    return {"Authorization": f"Bearer {token}"}


def _valid_email(email: str) -> bool:
    try:
        validate_email(email)
        return True
    except ValueError:
        return False


def try_multiple_user_combs(username_min_size: int = 1):
    strategy = given(
        username=st.text(
            min_size=username_min_size,
            max_size=50,
            alphabet=st.characters(
                exclude_categories=["Cs"], exclude_characters=["\x00"]
            ),
        ),
        email=st.emails().filter(_valid_email),
        password=st.text(
            min_size=8,
            max_size=200,
            alphabet=st.characters(
                exclude_categories=["Cs"], exclude_characters=["\x00"]
            ),
        ),
    )

    health_check = hypothesis_settings(
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )

    def decorator(func):
        return health_check(strategy(func))

    return decorator


async def clean_db(db: AsyncSession):
    # A helper for cleaning db in the start of hypothesis tests
    await db.execute(sql_delete(models.User))
    await db.execute(sql_delete(models.LoginLog))
