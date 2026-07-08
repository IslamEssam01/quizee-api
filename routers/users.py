from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

import models
from database import DBSession
from schemas.user import UserCreate, UserPrivate
from utils.auth import hash_password
from utils.error_messages import UserErrors

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
