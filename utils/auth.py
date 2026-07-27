import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import models
from config import settings
from database import DBSession
from utils.constants import REFRESH_TOKEN_COOKIE_KEY
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


AccessToken = Annotated[str, Depends(oauth2_scheme)]


async def get_current_user(token: AccessToken, db: DBSession):
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


def issue_refresh_token(db: AsyncSession, user_id: int, family_id: str | None = None):
    token = generate_random_token()
    db.add(
        models.RefreshToken(
            user_id=user_id,
            token_hash=hash_random_token(token),
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.refresh_token_expire_days),
            family_id=family_id if family_id else uuid4().hex,
        )
    )

    return token


def set_refresh_cookie(response: Response, token: str):
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE_KEY,
        value=token,
        httponly=True,
        secure=settings.env == "PRODUCTION",
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
    )


def delete_refresh_cookie(response: Response):
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE_KEY,
    )


def get_client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

    return request.client.host if request.client else ""


async def check_login_rate_limit(db: AsyncSession, email: str, ip_address: str):
    window_start = datetime.now(UTC) - timedelta(
        seconds=settings.login_rate_limit_max_seconds
    )

    count_result = await db.execute(
        select(func.count())
        .select_from(models.LoginLog)
        .where(
            or_(
                models.LoginLog.email == email, models.LoginLog.ip_address == ip_address
            )
        )
        .where(models.LoginLog.created_at >= window_start)
    )
    total_attempts = count_result.scalar() or 0

    if total_attempts >= settings.login_rate_limit_max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=AuthErrors.RATE_LIMIT_REACHED,
        )

    db.add(models.LoginLog(email=email, ip_address=ip_address))
    await db.commit()
