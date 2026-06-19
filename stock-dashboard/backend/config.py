"""
Konfiguration für das Aktien-Dashboard.
Lädt Einstellungen aus Umgebungsvariablen und .env Datei.
"""

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Zentrale Konfiguration — Werte werden aus ENV-Variablen gelesen."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Auth ---
    DASHBOARD_PASSWORD: str = "admin"
    SESSION_SECRET: str = secrets.token_hex(32)

    # --- LLM ---
    LLM_API_URL: str = "https://api.ai.rh-koeln.de/v1/chat/completions"
    LLM_MODEL: str = "mistral-large-3-675b-instruct-2512"
    LLM_API_KEY: str = ""

    # --- Datenbank ---
    DB_PATH: str = "/app/data/watchlist.db"

    # --- Cache ---
    CACHE_TTL: int = 300  # Sekunden (5 Minuten)


@lru_cache()
def get_settings() -> Settings:
    """Singleton-Zugriff auf die Einstellungen."""
    return Settings()
