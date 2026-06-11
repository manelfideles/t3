from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_token: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    gemini_fallback_model: str = "gemini-2.5-flash"
    database_url: str = "t3.db"
    google_client_id: str = ""
    google_client_secret: str = ""
    intervals_athlete_id: str = ""
    intervals_api_key: str = ""


settings = Settings()
