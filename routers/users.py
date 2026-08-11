from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, status
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, update

import models
from database import DBSession
from schemas.attempt import PaginatedUserAttemptResponse
from schemas.quiz import PaginatedQuizPrivateResponse, PaginatedQuizPublicResponse
from schemas.user import (
    ChangePasswordRequest,
    UserCreate,
    UserPrivate,
    UserPublic,
    UserUpdate,
)
from utils.auth import CurrentUser, hash_password, hash_random_token, verify_password
from utils.enums import Visibility
from utils.error_messages import UserErrors
from utils.quizzes import get_quizzes_with_options
from utils.success_messages import UserMessages

router = APIRouter()


@router.post("", response_model=UserPrivate, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: DBSession):
    result = await db.execute(
        select(models.User).where(func.lower(models.User.email) == user.email.lower())
    )

    existing_email = result.scalars().first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=UserErrors.DUPLICATE_EMAIL
        )

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

    new_user = models.User(
        username=user.username,
        email=user.email.lower(),
        password_hash=hash_password(user.password),
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.get("/me", response_model=UserPrivate)
async def get_current_user(current_user: CurrentUser):
    return current_user


@router.get("/me/quizzes", response_model=PaginatedQuizPrivateResponse)
async def get_current_user_quizzes(
    current_user: CurrentUser,
    db: DBSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    visibility: Annotated[Visibility | None, Query()] = None,
):
    return await get_quizzes_with_options(
        db=db,
        skip=skip,
        limit=limit,
        owner_id=current_user.id,
        visibility=visibility,
        is_public=False,
    )


@router.get("/me/attempts", response_model=PaginatedUserAttemptResponse)
async def get_current_user_attempts(
    current_user: CurrentUser,
    db: DBSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    result = await db.execute(
        select(models.Attempt)
        .where(models.Attempt.user_id == current_user.id)
        .order_by(models.Attempt.started_at.desc())
        .offset(skip)
        .limit(limit)
    )
    attempts = result.scalars().all()

    count_result = await db.execute(
        select(func.count())
        .select_from(models.Attempt)
        .where(models.Attempt.user_id == current_user.id)
    )

    total = count_result.scalar() or 0

    has_more = skip + limit < total

    return {
        "skip": skip,
        "limit": limit,
        "total": total,
        "has_more": has_more,
        "attempts": attempts,
    }


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(user_id: int, db: DBSession):
    result = await db.execute(select(models.User).where(models.User.id == user_id))

    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=UserErrors.USER_NOT_FOUND
        )

    return user


@router.get("/{user_id}/quizzes", response_model=PaginatedQuizPublicResponse)
async def get_user_quizzes(
    user_id: int,
    db: DBSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return await get_quizzes_with_options(
        db=db, skip=skip, limit=limit, owner_id=user_id, visibility=Visibility.PUBLIC
    )


@router.patch("/me/password")
async def update_current_user_password(
    current_user: CurrentUser,
    request_data: ChangePasswordRequest,
    db: DBSession,
    refresh_token_cookie: Annotated[str | None, Cookie(alias="refresh_token")] = None,
    x_client_type: Annotated[str, Header()] = "web",
):
    if not verify_password(request_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=UserErrors.INCORRECT_CURRENT_PASSWORD,
        )

    refresh_token = (
        refresh_token_cookie if x_client_type == "web" else request_data.refresh_token
    )

    current_user.password_hash = hash_password(request_data.new_password)

    if request_data.logout_all_sessions:
        await db.execute(
            update(models.RefreshToken)
            .where(models.RefreshToken.user_id == current_user.id)
            .where(
                models.RefreshToken.token_hash != hash_random_token(refresh_token or "")
            )
            .values(revoked_at=datetime.now(UTC))
        )

    await db.execute(
        sql_delete(models.PasswordResetToken).where(
            models.PasswordResetToken.user_id == current_user.id
        )
    )
    await db.commit()

    return {"message": UserMessages.PASSWORD_UPDATED_SUCCESSFULLY}


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


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, current_user: CurrentUser, db: DBSession):
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=UserErrors.NOT_AUTHORIZED_TO_DELETE_USER,
        )

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=UserErrors.USER_NOT_FOUND
        )

    await db.delete(user)
    await db.commit()
