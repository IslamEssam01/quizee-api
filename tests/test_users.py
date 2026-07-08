import pytest
from httpx import AsyncClient
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

import models


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
