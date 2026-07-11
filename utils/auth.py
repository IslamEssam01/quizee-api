from datetime import UTC, datetime, timedelta

import jwt
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

from config import settings

password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/swagger-login")


def hash_password(password: str):
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str):
    return password_hash.verify(plain_password, hashed_password)


def create_access_token(user_id: int):
    to_encode = {
        "sub": str(user_id),
        "exp": datetime.now(UTC)
        + timedelta(minutes=settings.access_token_expire_minutes),
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
