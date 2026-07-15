from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Response,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, update

import models
from config import settings
from database import DBSession
from schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    Token,
)
from utils.auth import (
    create_access_token,
    generate_random_token,
    hash_password,
    hash_random_token,
    issue_refresh_token,
    set_refresh_cookie,
    verify_password,
)
from utils.email import send_reset_password_email
from utils.error_messages import AuthErrors
from utils.success_messages import AuthMessages

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
        select(models.RefreshToken)
        .where(models.RefreshToken.token_hash == hash_random_token(token))
        .with_for_update()
    )

    refresh_token_db = result.scalars().first()

    if not refresh_token_db or refresh_token_db.revoked_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrors.INVALID_TOKEN,
        )

    if refresh_token_db.expires_at < datetime.now(UTC):
        refresh_token_db.revoked_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrors.INVALID_TOKEN,
        )

    if refresh_token_db.rotated_at:
        await db.execute(
            update(models.RefreshToken)
            .where(models.RefreshToken.family_id == refresh_token_db.family_id)
            .values(revoked_at=datetime.now(UTC))
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrors.INVALID_TOKEN,
        )
        # TODO: send an email to the user signaling there might be theft

    user_id = refresh_token_db.user_id

    refresh_token_db.rotated_at = datetime.now(UTC)

    new_refresh_token = issue_refresh_token(
        db, refresh_token_db.user_id, refresh_token_db.family_id
    )

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
        select(models.RefreshToken)
        .where(models.RefreshToken.token_hash == hash_random_token(refresh_token))
        .with_for_update()
    )
    refresh_token_db = result.scalars().first()

    if not refresh_token_db:
        return

    await db.execute(
        update(models.RefreshToken)
        .where(models.RefreshToken.family_id == refresh_token_db.family_id)
        .values(revoked_at=datetime.now(UTC))
    )

    await db.commit()


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    request_data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: DBSession,
):

    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == request_data.email.lower()
        )
    )
    user = result.scalars().first()

    if user:
        await db.execute(
            sql_delete(models.PasswordResetToken).where(
                models.PasswordResetToken.user_id == user.id
            )
        )

        token = generate_random_token()
        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token_hash=hash_random_token(token),
            expires_at=datetime.now(UTC)
            + timedelta(minutes=settings.reset_token_expire_minutes),
        )
        db.add(reset_token)
        await db.commit()
        background_tasks.add_task(
            send_reset_password_email,
            email_to=user.email,
            username=user.username,
            token=token,
        )

    return {"message": AuthMessages.PASSWORD_RESET_REQUESTED}


@router.post("/reset-password")
async def reset_password(request_data: ResetPasswordRequest, db: DBSession):
    result = await db.execute(
        select(models.PasswordResetToken).where(
            models.PasswordResetToken.token_hash
            == hash_random_token(request_data.token)
        )
    )
    reset_token = result.scalars().first()

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=AuthErrors.INVALID_TOKEN
        )

    if reset_token.expires_at < datetime.now(UTC):
        await db.delete(reset_token)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=AuthErrors.INVALID_TOKEN
        )

    result = await db.execute(
        select(models.User).where(models.User.id == reset_token.user_id)
    )
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=AuthErrors.INVALID_TOKEN
        )

    await db.execute(
        sql_delete(models.PasswordResetToken).where(
            models.PasswordResetToken.user_id == user.id
        )
    )
    await db.execute(
        sql_delete(models.RefreshToken).where(models.RefreshToken.user_id == user.id)
    )
    user.password_hash = hash_password(request_data.new_password)

    await db.commit()

    return {"message": AuthMessages.PASSWORD_RESET_SUCCESSFULLY}


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
