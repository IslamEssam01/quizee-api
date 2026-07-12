from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

import models
from database import DBSession
from schemas.auth import LoginRequest, RefreshTokenRequest, Token
from utils.auth import (
    create_access_token,
    hash_random_token,
    issue_refresh_token,
    set_refresh_cookie,
    verify_password,
)
from utils.error_messages import AuthErrors

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(
    credentials: LoginRequest,
    db: DBSession,
    response: Response,
    x_client_type: Annotated[str, Header()] = "web",
):
    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == credentials.email.lower()
        )
    )
    user = result.scalars().first()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrors.INCORRECT_EMAIL_OR_PASSWORD,
        )

    new_refresh_token = issue_refresh_token(db, user.id)

    await db.commit()

    if x_client_type == "web":
        set_refresh_cookie(response, new_refresh_token)

    return Token(
        access_token=create_access_token(user.id),
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    db: DBSession,
    response: Response,
    request_data: RefreshTokenRequest | None = None,
    refresh_token_cookie: Annotated[str | None, Cookie(alias="refresh_token")] = None,
    x_client_type: Annotated[str, Header()] = "web",
):
    token = (
        refresh_token_cookie
        if x_client_type == "web"
        else (request_data.refresh_token if request_data else None)
    )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrors.REFRESH_TOKEN_MISSING,
        )

    result = await db.execute(
        select(models.RefreshToken).where(
            models.RefreshToken.token_hash == hash_random_token(token)
        )
    )

    refresh_token_db = result.scalars().first()

    if not refresh_token_db:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrors.INVALID_TOKEN,
        )

    if refresh_token_db.expires_at < datetime.now(UTC):
        await db.delete(refresh_token_db)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrors.INVALID_TOKEN,
        )

    user_id = refresh_token_db.user_id

    await db.delete(refresh_token_db)

    new_refresh_token = issue_refresh_token(db, refresh_token_db.user_id)

    await db.commit()

    if x_client_type == "web":
        set_refresh_cookie(response, new_refresh_token)

    return Token(
        access_token=create_access_token(user_id),
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    db: DBSession,
    request_data: RefreshTokenRequest | None = None,
    refresh_token_cookie: Annotated[str | None, Cookie(alias="refresh_token")] = None,
    x_client_type: Annotated[str, Header()] = "web",
):
    refresh_token = (
        refresh_token_cookie
        if x_client_type == "web"
        else (request_data.refresh_token if request_data else None)
    )

    if not refresh_token:
        return

    result = await db.execute(
        select(models.RefreshToken).where(
            models.RefreshToken.token_hash == hash_random_token(refresh_token)
        )
    )
    refresh_token_db = result.scalars().first()

    if not refresh_token_db:
        return

    await db.delete(refresh_token_db)
    await db.commit()


@router.post("/swagger-login", response_model=Token, include_in_schema=False)
async def swagger_login(
    credentials: Annotated[OAuth2PasswordRequestForm, Depends()], db: DBSession
):
    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == credentials.username.lower()
        )
    )
    user = result.scalars().first()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrors.INCORRECT_EMAIL_OR_PASSWORD,
        )

    new_refresh_token = issue_refresh_token(db, user.id)

    await db.commit()

    return Token(
        access_token=create_access_token(user.id),
        refresh_token=new_refresh_token,
        token_type="bearer",
    )
