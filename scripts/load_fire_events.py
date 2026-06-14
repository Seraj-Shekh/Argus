"""
Load and parse EFFIS historical fire event records for Finland from 2015 onwards.
Outputs a cleaned DataFrame and saves it to data/fire_events_clean.csv.
"""

import json
import os
from pathlib import Path

import pandas as pd


FIRE_EVENTS_PATH = Path(__file__).parent.parent / "fire_events.json"
OUTPUT_DIR = Path(__file__).parent.parent / "data"
OUTPUT_PATH = OUTPUT_DIR / "fire_events_clean.csv"

# Only keep events with confidence >= 80 (EFFIS standard threshold)
MIN_CONFIDENCE = 80
START_YEAR = 2015


def load_effis_events(filepath: Path) -> pd.DataFrame:
    with open(filepath, "r", encoding="utf-8") as f:
        geojson = json.load(f)

    records = []
    for feature in geojson["features"]:
        props = feature["properties"]
        records.append({
            "date": props["acq_at_s"],
            "lat": props["lat"],
            "lon": props["lon"],
            "frp": props["frp"],          # Fire Radiative Power (MW)
            "confidence": props["confidence"],
            "night": props["night"],
            "satellite": props["satellite"].strip(),
        })

    df = pd.DataFrame(records)

    # Parse datetime and extract date only
    df["datetime"] = pd.to_datetime(df["date"], format="%Y-%m-%d %H:%M:%S")
    df["date"] = df["datetime"].dt.date
    df["year"] = df["datetime"].dt.year

    return df


def clean_events(df: pd.DataFrame) -> pd.DataFrame:
    initial_count = len(df)

    # Filter to 2015+
    df = df[df["year"] >= START_YEAR].copy()

    # Drop low-confidence detections
    df = df[df["confidence"] >= MIN_CONFIDENCE].copy()

    # Drop rows missing coordinates
    df = df.dropna(subset=["lat", "lon"])

    # Validate coordinate bounds for Finland (rough bounding box)
    df = df[
        (df["lat"].between(59.5, 70.1)) &
        (df["lon"].between(19.0, 31.6))
    ].copy()

    print(f"Loaded {initial_count} raw records")
    print(f"After filtering: {len(df)} records")
    print(f"Date range: {df['date'].min()} to {df['date'].max()}")
    print(f"Unique fire dates: {df['date'].nunique()}")

    return df[["date", "lat", "lon", "frp", "confidence", "night", "satellite"]].reset_index(drop=True)


def main():
    print(f"Reading EFFIS data from {FIRE_EVENTS_PATH}")
    df = load_effis_events(FIRE_EVENTS_PATH)
    df = clean_events(df)

    OUTPUT_DIR.mkdir(exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Saved {len(df)} fire events to {OUTPUT_PATH}")

    return df


if __name__ == "__main__":
    main()
