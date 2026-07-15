from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    db_url: str
    test_db_url: str
    frontend_url: str
    secret_key: SecretStr
    algorithm: str = "HS256"
    env: str
    mail_from: str = "example@example.com"
    smtp_server: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    access_token_expire_minutes: int = 15
    reset_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    login_rate_limit_max_seconds: int = 60
    login_rate_limit_max_attempts: int = 5
    trust_proxy_headers: bool = False


settings = Settings()  # Will be loaded from .env   # pyright: ignore[reportCallIssue]
