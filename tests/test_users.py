import pytest
from httpx import AsyncClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

import models
from tests.conftest import auth_header, create_test_user, login_user
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
        min_size=2,
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
        json={"username": username, "email": email[1:], "password": password},
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


@pytest.mark.anyio
async def test_update_user_wrong_args(client: AsyncClient):
    email = "testemail@example.com"
    password = "testpass1"
    user = await create_test_user(client, "test user", email, password)
    token = await login_user(client, email, password)
    response = await client.patch(
        f"/api/users/{user["id"]}",
        json={"username": ""},
        headers=auth_header(token),
    )

    assert response.status_code == 422


@pytest.mark.anyio
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    username=st.text(
        min_size=2,
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
async def test_update_user_unauthorized(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    user1 = await create_test_user(client, username, email, password)
    user2 = await create_test_user(client, username[1:], email[1:], password)

    token2 = await login_user(client, user2["email"], password)

    response = await client.patch(
        f"/api/users/{user1["id"]}",
        headers=auth_header(token2),
        json={"username": "new username"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == UserErrors.NOT_AUTHORIZED_TO_UPDATE_USER


@pytest.mark.anyio
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    username=st.text(
        min_size=2,
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
async def test_update_duplicate_user(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    await create_test_user(client, username, email, password)
    user = await create_test_user(client, username[1:], email[1:], password)

    token = await login_user(client, user["email"], password)

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
async def test_update_user_successfully(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    user = await create_test_user(client, username, email, password)

    token = await login_user(client, user["email"], password)

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
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    username=st.text(
        min_size=2,
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
async def test_delete_user_unauthorized(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    user1 = await create_test_user(client, username, email, password)
    user2 = await create_test_user(client, username[1:], email[1:], password)

    token2 = await login_user(client, user2["email"], password)

    response = await client.delete(
        f"/api/users/{user1["id"]}",
        headers=auth_header(token2),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == UserErrors.NOT_AUTHORIZED_TO_DELETE_USER


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
async def test_delete_user_successfully(
    client: AsyncClient,
    db_session: AsyncSession,
    username: str,
    email: str,
    password: str,
):
    await db_session.execute(sql_delete(models.User))

    user = await create_test_user(client, username, email, password)

    token = await login_user(client, user["email"], password)

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
