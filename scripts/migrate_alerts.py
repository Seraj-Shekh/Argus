"""
Adds new columns to the existing alerts table.
Run once: python scripts/migrate_alerts.py
Safe to re-run — skips columns that already exist.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.database.session import engine

NEW_COLUMNS = [
    ("source",        "VARCHAR(20) NOT NULL DEFAULT 'software'"),
    ("risk_level",    "VARCHAR(20)"),
    ("wind_speed",    "DOUBLE PRECISION"),
    ("precipitation", "DOUBLE PRECISION"),
    ("station_lat",   "DOUBLE PRECISION"),
    ("station_lon",   "DOUBLE PRECISION"),
    ("ai_metadata",   "JSONB"),
]


def column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = :t AND column_name = :c
    """), {"t": table, "c": column})
    return result.fetchone() is not None


def main() -> None:
    with engine.begin() as conn:
        for col_name, col_def in NEW_COLUMNS:
            if column_exists(conn, "alerts", col_name):
                print(f"  skip  {col_name} (already exists)")
            else:
                conn.execute(text(f"ALTER TABLE alerts ADD COLUMN {col_name} {col_def}"))
                print(f"  added {col_name}")
    print("Migration complete.")


if __name__ == "__main__":
    main()
