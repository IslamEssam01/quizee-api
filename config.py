from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_url: str
    test_db_url: str


settings = Settings()  # Will be loaded from .env   # pyright: ignore[reportCallIssue]
