from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_token: str = ""
    gemini_api_key: str = ""
    database_url: str = "t3.db"


settings = Settings()
