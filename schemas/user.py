from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class UserUpdate(BaseModel):
    username: str | None = Field(min_length=1, max_length=50, default=None)
    email: str | None = Field(min_length=1, max_length=200, default=None)
    password: str | None = Field(min_length=8, max_length=200, default=None)


class UserPublic(BaseModel):
    id: int
    username: str


class UserPrivate(UserPublic):
    email: str
