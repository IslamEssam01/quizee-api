import pytest
from httpx import AsyncClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

import models
from tests.conftest import create_test_user
from utils.auth import verify_access_token


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
async def test_login(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    user = await create_test_user(client, username, email, password)

    response = await client.post(
        "/api/users/login", json={"email": email, "password": password}
    )

    assert response.status_code == 200
    data = response.json()

    assert data.keys() == {"access_token", "token_type"}

    token = data["access_token"]

    user_id = verify_access_token(token)
    assert user_id is not None
    assert int(user_id) == user["id"]
