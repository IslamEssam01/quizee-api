import pytest
from httpx import AsyncClient
from pydantic import validate_email
from sqlalchemy.ext.asyncio import AsyncSession

import models
from tests.conftest import (
    auth_header,
    clean_db,
    create_test_user,
    login_user,
    try_multiple_user_combs,
)
from utils.auth import verify_access_token
from utils.error_messages import AuthErrors, UserErrors
from utils.success_messages import UserMessages


@pytest.mark.anyio
async def test_create_user_wrong_args(client: AsyncClient):
    response = await client.post("/api/users", json={"username": "test user"})

    assert response.status_code == 422


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_create_user_successfully(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await clean_db(db_session)
    response = await client.post(
        "/api/users", json={"username": username, "email": email, "password": password}
    )

    assert response.status_code == 201

    data = response.json()

    assert data.keys() == {"id", "username", "email"}
    assert data["username"] == username
    assert data["email"].lower() == validate_email(email)[1].lower()


@pytest.mark.anyio
@try_multiple_user_combs(username_min_size=2)
async def test_create_duplicate_user(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await clean_db(db_session)

    await create_test_user(client, username, email, password)

    response = await client.post(
        "/api/users",
        json={"username": username, "email": f"x{email}", "password": password},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == UserErrors.DUPLICATE_USERNAME

    response = await client.post(
        "/api/users",
        json={"username": username[1:], "email": email, "password": password},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == UserErrors.DUPLICATE_EMAIL


@pytest.mark.anyio
async def test_get_user_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await clean_db(db_session)

    response = await client.get("/api/users/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == UserErrors.USER_NOT_FOUND


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_get_user_successfully(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await clean_db(db_session)

    user = await create_test_user(client, username, email, password)

    response = await client.get(f"/api/users/{user["id"]}")

    assert response.status_code == 200

    data = response.json()

    assert data.keys() == {"id", "username"}

    assert data["id"] == user["id"]
    assert data["username"] == user["username"]


@pytest.mark.anyio
async def test_update_user_wrong_args(client: AsyncClient):
    email = "testemail@example.com"
    password = "testpass1"
    user = await create_test_user(client, "test user", email, password)
    token, _ = await login_user(client, email, password)
    response = await client.patch(
        f"/api/users/{user["id"]}",
        json={"username": ""},
        headers=auth_header(token),
    )

    assert response.status_code == 422


@pytest.mark.anyio
@try_multiple_user_combs(username_min_size=2)
async def test_update_user_unauthorized(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await clean_db(db_session)

    user1 = await create_test_user(client, username, email, password)
    user2 = await create_test_user(client, username[1:], f"x{email}", password)

    token2, _ = await login_user(client, user2["email"], password)

    response = await client.patch(
        f"/api/users/{user1["id"]}",
        headers=auth_header(token2),
        json={"username": "new username"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == UserErrors.NOT_AUTHORIZED_TO_UPDATE_USER


@pytest.mark.anyio
@try_multiple_user_combs(username_min_size=2)
async def test_update_duplicate_user(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await clean_db(db_session)

    await create_test_user(client, username, email, password)
    user = await create_test_user(client, username[1:], f"x{email}", password)

    token, _ = await login_user(client, user["email"], password)

    response = await client.patch(
        f"/api/users/{user["id"]}",
        headers=auth_header(token),
        json={"username": username},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == UserErrors.DUPLICATE_USERNAME

    response = await client.patch(
        f"/api/users/{user["id"]}",
        headers=auth_header(token),
        json={"email": email},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == UserErrors.DUPLICATE_EMAIL


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_update_user_successfully(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await clean_db(db_session)

    user = await create_test_user(client, username, email, password)

    token, _ = await login_user(client, user["email"], password)

    new_username = "new username"
    new_email = "newemail@test.com"
    response = await client.patch(
        f"/api/users/{user["id"]}",
        headers=auth_header(token),
        json={"username": new_username, "email": new_email},
    )

    assert response.status_code == 200

    data = response.json()

    assert data.keys() == {"id", "username", "email"}

    assert data["username"] == new_username
    assert data["email"] == new_email


@pytest.mark.anyio
@try_multiple_user_combs(username_min_size=2)
async def test_delete_user_unauthorized(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await clean_db(db_session)

    user1 = await create_test_user(client, username, email, password)
    user2 = await create_test_user(client, username[1:], f"x{email}", password)

    token2, _ = await login_user(client, user2["email"], password)

    response = await client.delete(
        f"/api/users/{user1["id"]}",
        headers=auth_header(token2),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == UserErrors.NOT_AUTHORIZED_TO_DELETE_USER


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_delete_user_successfully(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await clean_db(db_session)

    user = await create_test_user(client, username, email, password)

    token, _ = await login_user(client, user["email"], password)

    response = await client.delete(
        f"/api/users/{user["id"]}",
        headers=auth_header(token),
    )

    assert response.status_code == 204

    response = await client.get(
        f"/api/users/{user["id"]}",
    )

    assert response.status_code == 404
    assert response.json()["detail"] == UserErrors.USER_NOT_FOUND


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_get_current_user(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await clean_db(db_session)

    user = await create_test_user(client, username, email, password)
    token, _ = await login_user(client, email, password)

    response = await client.get(
        "/api/users/me",
        headers=auth_header(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data.keys() == {"id", "username", "email"}
    assert data["id"] == user["id"]
    assert data["username"] == username
    assert data["email"].lower() == user["email"]


@pytest.mark.anyio
async def test_change_password_invalid_current_password(
    client: AsyncClient,
):
    await create_test_user(client)
    token, _ = await login_user(client)

    response = await client.patch(
        "/api/users/me/password",
        json={
            "current_password": "incorrect password",
            "new_password": "doesn't matter",
        },
        headers=auth_header(token),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == UserErrors.INCORRECT_CURRENT_PASSWORD


@pytest.mark.anyio
@try_multiple_user_combs()
async def test_change_password(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await clean_db(db_session)

    user = await create_test_user(client, username, email, password)
    token, _ = await login_user(client, email, password)

    new_password = password[:-1].rjust(8, "0")
    response = await client.patch(
        "/api/users/me/password",
        json={"current_password": password, "new_password": new_password},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["message"] == UserMessages.PASSWORD_UPDATED_SUCCESSFULLY

    if new_password != password:
        response = await client.post(
            "/api/auth/login",
            json={
                "email": email,
                "password": password,
            },
        )

        assert response.status_code == 401
        assert response.json()["detail"] == AuthErrors.INCORRECT_EMAIL_OR_PASSWORD

    response = await client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": new_password,
        },
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
async def test_change_password_with_multi_logout(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await clean_db(db_session)

    await create_test_user(client, username, email, password)
    token, _ = await login_user(client, email, password, "web")
    _, refresh_token2 = await login_user(client, email, password, "test")

    new_password = password[:-1].rjust(8, "0")
    response = await client.patch(
        "/api/users/me/password",
        json={
            "current_password": password,
            "new_password": new_password,
            "logout_all_sessions": True,
        },
        headers=auth_header(token),
    )

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token2},
        headers={"X-Client-Type": "test"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == AuthErrors.INVALID_TOKEN

    response = await client.post(
        "/api/auth/refresh",
        headers={"X-Client-Type": "web"},
    )

    assert response.status_code == 200
