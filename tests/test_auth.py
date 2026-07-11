from datetime import timedelta
from time import sleep

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

import models
from database import DBSession
from tests.conftest import auth_header, create_test_user
from utils.auth import create_access_token, get_current_user, verify_access_token
from utils.error_messages import AuthErrors


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
        "/api/auth/login", json={"email": email, "password": password}
    )

    assert response.status_code == 200
    data = response.json()

    assert data.keys() == {"access_token", "token_type"}

    token = data["access_token"]

    user_id = verify_access_token(token)
    assert user_id is not None
    assert int(user_id) == user["id"]


@pytest.mark.anyio
async def test_invalid_access_token(db_session: AsyncSession):

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user("invalid token", db_session)

    exception_value = exc_info.value

    assert exception_value.status_code == 401
    assert exception_value.detail == AuthErrors.INVALID_TOKEN


@pytest.mark.anyio
async def test_expired_access_token(db_session: AsyncSession):
    token = create_access_token(999, timedelta(milliseconds=1))
    sleep(1)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token, db_session)

    exception_value = exc_info.value

    assert exception_value.status_code == 401
    assert exception_value.detail == AuthErrors.INVALID_TOKEN


@pytest.mark.anyio
async def test_user_not_found(db_session: AsyncSession):
    token = create_access_token(999)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token, db_session)

    exception_value = exc_info.value

    assert exception_value.status_code == 401
    assert exception_value.detail == AuthErrors.USER_NOT_FOUND
