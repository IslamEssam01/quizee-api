import pytest
from httpx import AsyncClient
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

import models
from tests.conftest import create_test_user
from utils.error_messages import UserErrors


@pytest.mark.anyio
async def test_create_user_wrong_args(client: AsyncClient):
    response = await client.post("/api/users", json={"username": "test user"})

    assert response.status_code == 422


@pytest.mark.anyio
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    username=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(exclude_categories=["Cs"], exclude_characters=["\x00"]),
    ),
    email=st.emails(),
    password=st.text(
        min_size=8,
        max_size=200,
        alphabet=st.characters(exclude_categories=["Cs"], exclude_characters=["\x00"]),
    ),
)
async def test_create_user_successfully(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))
    response = await client.post(
        "/api/users", json={"username": username, "email": email, "password": password}
    )

    assert response.status_code == 201

    data = response.json()

    assert data.keys() == {"id", "username", "email"}
    assert data["username"] == username
    assert data["email"].lower() == email.lower()


@pytest.mark.anyio
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    username=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(exclude_categories=["Cs"], exclude_characters=["\x00"]),
    ),
    email=st.emails(),
    password=st.text(
        min_size=8,
        max_size=200,
        alphabet=st.characters(exclude_categories=["Cs"], exclude_characters=["\x00"]),
    ),
)
async def test_create_duplicate_user(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    await create_test_user(client, username, email, password)

    response = await client.post(
        "/api/users",
        json={"username": username, "email": "different" + email, "password": password},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == UserErrors.DUPLICATE_USERNAME

    response = await client.post(
        "/api/users",
        json={"username": "different" + username, "email": email, "password": password},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == UserErrors.DUPLICATE_EMAIL


@pytest.mark.anyio
async def test_get_user_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await db_session.execute(sql_delete(models.User))

    response = await client.get("/api/users/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == UserErrors.USER_NOT_FOUND


@pytest.mark.anyio
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    username=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(exclude_categories=["Cs"], exclude_characters=["\x00"]),
    ),
    email=st.emails(),
    password=st.text(
        min_size=8,
        max_size=200,
        alphabet=st.characters(exclude_categories=["Cs"], exclude_characters=["\x00"]),
    ),
)
async def test_get_user_successfully(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    user = await create_test_user(client, username, email, password)

    response = await client.get(f"/api/users/{user["id"]}")

    assert response.status_code == 200

    data = response.json()

    assert data.keys() == {"id", "username"}

    assert data["id"] == user["id"]
    assert data["username"] == user["username"]
