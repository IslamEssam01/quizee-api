from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

import models
from database import DBSession
from schemas.auth import LoginRequest, Token
from schemas.user import UserCreate, UserPrivate, UserPublic, UserUpdate
from utils.auth import CurrentUser, create_access_token, hash_password, verify_password
from utils.error_messages import AuthErrors, UserErrors

router = APIRouter()


@router.post("", response_model=UserPrivate, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: DBSession):
    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.username) == user.username.lower()
        )
    )

    existing_username = result.scalars().first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=UserErrors.DUPLICATE_USERNAME
        )

    result = await db.execute(
        select(models.User).where(func.lower(models.User.email) == user.email.lower())
    )

    existing_email = result.scalars().first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=UserErrors.DUPLICATE_EMAIL
        )

    new_user = models.User(
        username=user.username,
        email=user.email.lower(),
        password_hash=hash_password(user.password),
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


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


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(user_id: int, db: DBSession):
    result = await db.execute(select(models.User).where(models.User.id == user_id))

    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=UserErrors.USER_NOT_FOUND
        )

    return user


@router.patch("/{user_id}", response_model=UserPrivate)
async def update_user(
    user_id: int, current_user: CurrentUser, user_update: UserUpdate, db: DBSession
):
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=UserErrors.NOT_AUTHORIZED_TO_UPDATE_USER,
        )

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=UserErrors.USER_NOT_FOUND
        )

    if user_update.username and user_update.username.lower() != user.username.lower():
        result = await db.execute(
            select(models.User).where(
                func.lower(models.User.username) == user_update.username.lower()
            )
        )
        existing_username = result.scalars().first()

        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=UserErrors.DUPLICATE_USERNAME,
            )

        user.username = user_update.username

    if user_update.email and user_update.email.lower() != user.email.lower():
        result = await db.execute(
            select(models.User).where(
                func.lower(models.User.email) == user_update.email.lower()
            )
        )
        existing_email = result.scalars().first()

        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=UserErrors.DUPLICATE_EMAIL,
            )

        user.email = user_update.email.lower()

    await db.commit()
    await db.refresh(user)

    return user
