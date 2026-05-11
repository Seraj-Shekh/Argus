"""Small helper script to create database tables for development.

Run this script after configuring `DATABASE_URL` in `.env` to create the
`weather_observations` table.
"""
from app.database.session import Base, engine


def main() -> None:  # pragma: no cover - simple CLI helper
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Done.")


if __name__ == "__main__":
    main()
