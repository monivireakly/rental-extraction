from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required
    telegram_bot_token: str
    anthropic_api_key: str

    # Optional with defaults
    database_path: str = "./data/listings.db"
    telegram_channels: str = "condoapartmentincambodia"
    crawl_interval_hours: int = 6
    crawl_pages_per_run: int = 3

    @property
    def channels(self) -> list[str]:
        return [c.strip().lstrip("@") for c in self.telegram_channels.split(",") if c.strip()]


settings = Settings()
