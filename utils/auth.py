import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import models
from config import settings
from database import DBSession
from utils.error_messages import AuthErrors

password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/swagger-login")


def generate_random_token():
    return secrets.token_urlsafe(32)


def hash_random_token(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str):
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str):
    return password_hash.verify(plain_password, hashed_password)


def create_access_token(
    user_id: int,
    expires_delta: timedelta | None = None,
):
    expires_delta = (
        expires_delta
        if expires_delta
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode = {
        "sub": str(user_id),
        "exp": (datetime.now(UTC) + expires_delta),
    }

    token = jwt.encode(
        to_encode,
        key=settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm,
    )

    return token


def verify_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(
            token,
            key=settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"require": ["sub", "exp"]},
        )
    except jwt.InvalidTokenError:
        return None
    else:
        return payload.get("sub")


current_user_error_headers = {"WWW-Authenticate": "Bearer"}


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: DBSession
):
    user_id = verify_access_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrors.INVALID_TOKEN,
            headers=current_user_error_headers,
        )
    try:
        user_id_int = int(user_id)
    except TypeError, ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrors.INVALID_TOKEN,
            headers=current_user_error_headers,
        )

    result = await db.execute(select(models.User).where(models.User.id == user_id_int))
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrors.USER_NOT_FOUND,
            headers=current_user_error_headers,
        )

    return user


CurrentUser = Annotated[models.User, Depends(get_current_user)]


def issue_refresh_token(db: AsyncSession, user_id: int):
    token = generate_random_token()
    db.add(
        models.RefreshToken(
            user_id=user_id,
            token_hash=hash_random_token(token),
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.refresh_token_expire_days),
        )
    )

    return token


def set_refresh_cookie(response: Response, token: str):
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=settings.env == "PRODUCTION",
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
    )
