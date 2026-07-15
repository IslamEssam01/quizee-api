from datetime import timedelta
from time import sleep
from unittest.mock import ANY, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

import models
from tests.conftest import (
    auth_header,
    create_test_user,
    login_user,
    try_multiple_user_combs,
)
from utils.auth import create_access_token, get_current_user, verify_access_token
from utils.constants import REFRESH_TOKEN_COOKIE_KEY
from utils.error_messages import AuthErrors
from utils.success_messages import AuthMessages


@pytest.mark.anyio
async def test_login_incorrect_email(
    client: AsyncClient,
):
    await create_test_user(client)

    response = await client.post(
        "/api/auth/login",
        json={
            "email": "notreal@example.com",
            "password": "test pass",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == AuthErrors.INCORRECT_EMAIL_OR_PASSWORD


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_login_incorrect_password(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    await create_test_user(client, username, email, password)

    response = await client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": (
                "wrong password"
                if password != "wrong password"
                else "really wrong password"
            ),
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == AuthErrors.INCORRECT_EMAIL_OR_PASSWORD


@pytest.mark.anyio
@try_multiple_user_combs()
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

    assert data.keys() == {"access_token", "refresh_token", "token_type"}

    token = data["access_token"]

    user_id = verify_access_token(token)
    assert user_id is not None
    assert int(user_id) == user["id"]


@pytest.mark.anyio
async def test_invalid_refresh(
    client: AsyncClient,
):
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": "invalid token"},
        headers={"X-Client-Type": "test"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == AuthErrors.INVALID_TOKEN


@pytest.mark.anyio
async def test_missing_refresh(
    client: AsyncClient,
):
    response = await client.post(
        "/api/auth/refresh",
        headers={"X-Client-Type": "test"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == AuthErrors.REFRESH_TOKEN_MISSING


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_refresh_web_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    user = await create_test_user(client, username, email, password)

    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-Client-Type": "web"},
    )

    assert REFRESH_TOKEN_COOKIE_KEY in response.cookies
    response = await client.post(
        "/api/auth/refresh",
        headers={"X-Client-Type": "web"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data.keys() == {"access_token", "refresh_token", "token_type"}

    token = data["access_token"]

    user_id = verify_access_token(token)
    assert user_id is not None
    assert int(user_id) == user["id"]


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_refresh(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    user = await create_test_user(client, username, email, password)

    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-Client-Type": "test"},
    )

    data = response.json()
    refresh_token = data["refresh_token"]

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"X-Client-Type": "test"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data.keys() == {"access_token", "refresh_token", "token_type"}

    token = data["access_token"]

    user_id = verify_access_token(token)
    assert user_id is not None
    assert int(user_id) == user["id"]


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_refresh_rotation(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    await create_test_user(client, username, email, password)

    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-Client-Type": "test"},
    )

    data = response.json()
    refresh_token = data["refresh_token"]

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"X-Client-Type": "test"},
    )

    # This token should be rotated and not accepted
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"X-Client-Type": "test"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == AuthErrors.INVALID_TOKEN


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_refresh_resue_detection(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    await create_test_user(client, username, email, password)

    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-Client-Type": "test"},
    )

    data = response.json()
    refresh_token = data["refresh_token"]

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"X-Client-Type": "test"},
    )
    data = response.json()
    new_refresh_token = data["refresh_token"]

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"X-Client-Type": "test"},
    )

    # Assert that all tokens from the same login session got revoked
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": new_refresh_token},
        headers={"X-Client-Type": "test"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == AuthErrors.INVALID_TOKEN


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


@pytest.mark.anyio
async def test_logout_without_logging_in(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await db_session.execute(sql_delete(models.User))

    response = await client.post(
        "/api/auth/logout",
        headers={"X-Client-Type": "test"},
    )

    assert response.status_code == 204


@pytest.mark.anyio
async def test_logout_without_logging_in_web_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await db_session.execute(sql_delete(models.User))

    response = await client.post(
        "/api/auth/logout",
        headers={"X-Client-Type": "web"},
    )

    assert response.status_code == 204
    assert REFRESH_TOKEN_COOKIE_KEY not in response.cookies


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_logout(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    await create_test_user(client, username, email, password)

    await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-Client-Type": "test"},
    )

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_logout_web_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    await create_test_user(client, username, email, password)

    await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-Client-Type": "web"},
    )

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    assert REFRESH_TOKEN_COOKIE_KEY not in response.cookies


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_forgot_password(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    user = await create_test_user(client, username, email, password)

    with patch(
        "routers.auth.send_reset_password_email", autospec=True
    ) as mock_send_reset_password_email:
        response = await client.post("/api/auth/forgot-password", json={"email": email})

    assert response.status_code == 202
    assert response.json()["message"] == AuthMessages.PASSWORD_RESET_REQUESTED

    mock_send_reset_password_email.assert_awaited_once_with(
        email_to=user["email"], username=username, token=ANY
    )


@pytest.mark.anyio
async def test_reset_password_invalid_token(client: AsyncClient):
    response = await client.post(
        "/api/auth/reset-password",
        json={"token": "not a valid token", "new_password": "testing password"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == AuthErrors.INVALID_TOKEN


@pytest.mark.anyio
async def test_reset_password_deleted_user(client: AsyncClient):
    user = await create_test_user(client, password="testpass")
    access_token, _ = await login_user(client, user["email"], "testpass")

    with patch(
        "routers.auth.send_reset_password_email", autospec=True
    ) as mock_send_reset_password_email:
        await client.post("/api/auth/forgot-password", json={"email": user["email"]})

        token = (
            mock_send_reset_password_email.await_args.kwargs["token"]
            if mock_send_reset_password_email.await_args
            else ""
        )

        await client.delete(
            f"/api/users/{user["id"]}", headers=auth_header(access_token)
        )

        response = await client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": "testing password"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == AuthErrors.INVALID_TOKEN


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_reset_password(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    user = await create_test_user(client, username, email, password)

    with patch(
        "routers.auth.send_reset_password_email", autospec=True
    ) as mock_send_reset_password_email:
        await client.post("/api/auth/forgot-password", json={"email": email})

        token = (
            mock_send_reset_password_email.await_args.kwargs["token"]
            if mock_send_reset_password_email.await_args
            else ""
        )

        new_password = "new password"
        response = await client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": new_password},
        )

        assert response.status_code == 200
        assert response.json()["message"] == AuthMessages.PASSWORD_RESET_SUCCESSFULLY

        response = await client.post(
            "/api/auth/login",
            json={
                "email": email,
                "password": new_password,
            },
        )

        assert response.status_code == 200
        data = response.json()

        access_token = data["access_token"]

        user_id = verify_access_token(access_token)
        assert user_id is not None
        assert int(user_id) == user["id"]
