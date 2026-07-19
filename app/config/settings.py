"""Application settings loaded from environment variables.

This module uses `python-dotenv` to load `.env` during development and builds
the SQLAlchemy connection URL from separate PostgreSQL variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


def build_database_url(host: str, port: str, name: str, user: str, password: str) -> str:
    """Build a SQLAlchemy PostgreSQL URL from simple environment variables."""

    return (
        f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{name}"
    )


@dataclass(frozen=True)
class Settings:
    """Typed application settings.

    - `database_url`: SQLAlchemy connection URL (built from DB_* vars)
    - `fmi_base_url`: FMI Open Data WFS base URL
    - `openai_api_key`: OpenAI API key for alert generation
    - `env`: application environment (development/production)
    """

    database_url: str
    fmi_base_url: str = "https://opendata.fmi.fi/wfs"
    openai_api_key: str = ""
    env: str = "development"


def get_settings() -> Settings:
    """Read environment variables and return validated settings.

    Supports either:
    - `DATABASE_URL` directly, or
    - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
    """

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        db_host = os.getenv("DB_HOST")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME")
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")

        missing = [
            name
            for name, value in (
                ("DB_HOST", db_host),
                ("DB_NAME", db_name),
                ("DB_USER", db_user),
                ("DB_PASSWORD", db_password),
            )
            if not value
        ]
        if missing:
            missing_vars = ", ".join(missing)
            raise ValueError(
                "Missing database configuration. Set DATABASE_URL or these "
                f"variables in .env: {missing_vars}"
            )

        database_url = build_database_url(db_host, db_port, db_name, db_user, db_password)

    return Settings(
        database_url=database_url,
        fmi_base_url=os.getenv("FMI_BASE_URL", "https://opendata.fmi.fi/wfs"),
        openai_api_key=os.getenv("OPEN_AI_API_KEY", ""),
        env=os.getenv("ENV", "development"),
    )


settings = get_settings()
