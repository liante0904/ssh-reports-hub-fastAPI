from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "prod"
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60 * 24, ge=5, le=60 * 24 * 30)
    telegram_bot_token: str = ""
    telegram_auth_max_age_seconds: int = Field(default=60 * 60 * 24, ge=60, le=60 * 60 * 24 * 7)
    cors_allow_origins: str = (
        "https://ssh-private-hub.netlify.app,"
        "https://ssh-oci.netlify.app,"
        "https://ssh-oci.duckdns.org,"
        "http://localhost:5174,"
        "http://localhost:5173,"
        "http://localhost:3000,"
        "http://localhost:8888"
    )
    allowed_telegram_user_ids: str = ""
    rate_limit_default: str = "120/minute"
    rate_limit_auth: str = "10/minute"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def clean_telegram_bot_token(self) -> str:
        return self.telegram_bot_token.strip().strip('"').strip("'")

    @property
    def jwt_is_configured(self) -> bool:
        return len(self.jwt_secret_key) >= 32

    @property
    def telegram_allowed_user_ids(self) -> set[int]:
        raw = self.allowed_telegram_user_ids.strip()
        if not raw:
            return set()

        allowed_ids: set[int] = set()
        for part in raw.split(","):
            value = part.strip()
            if not value:
                continue
            try:
                allowed_ids.add(int(value))
            except ValueError:
                continue
        return allowed_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()
