from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

import models
from database import DBSession
from schemas.auth import LoginRequest, Token
from utils.auth import create_access_token, verify_password
from utils.error_messages import AuthErrors

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(credentials: LoginRequest, db: DBSession):
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

    return Token(access_token=create_access_token(user.id), token_type="bearer")


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

    return Token(access_token=create_access_token(user.id), token_type="bearer")
