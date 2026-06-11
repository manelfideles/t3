import pytest

from t3.config import Settings


def test_config_default_db_url() -> None:
    s = Settings(telegram_token="", gemini_api_key="")
    assert s.database_url == "t3.db"


def test_config_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_TOKEN", "tg-test-token")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    s = Settings()
    assert s.telegram_token == "tg-test-token"
    assert s.gemini_api_key == "gemini-test-key"


def test_config_custom_db_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "/data/t3.db")
    s = Settings()
    assert s.database_url == "/data/t3.db"


def test_config_empty_token_is_valid() -> None:
    s = Settings(telegram_token="", gemini_api_key="")
    assert s.telegram_token == ""
