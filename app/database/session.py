"""SQLAlchemy engine, session and base declarative class.

Provide `engine`, `SessionLocal`, `Base` and a `get_db` dependency generator
for FastAPI routes.
"""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config.settings import settings


# Create the SQLAlchemy engine. For PostgreSQL we expect a URL like
# postgresql+psycopg2://user:password@host:port/dbname
engine = create_engine(settings.database_url, future=True)


# Session factory used to create DB sessions. `future=True` enables SQLAlchemy
# 2.0 style features while remaining compatible with sessionmaker patterns.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


# Base class for ORM models to inherit from
Base = declarative_base()


def get_db() -> Generator:
    """Yield a SQLAlchemy session for FastAPI dependency injection.

    Usage in FastAPI endpoints::

        from app.database.session import get_db
        def endpoint(db: Session = Depends(get_db)):
            ...

    The generator ensures the session is closed after the request completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
