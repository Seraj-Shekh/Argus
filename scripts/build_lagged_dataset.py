"""
Builds data/training_dataset_lagged.csv by adding days_since_rain and
temp_rolling_7d to every row of data/training_dataset.csv.

These two features were validated in scripts/analyze_lagged_features.py on a
month-matched sample: both differentiate fire from non-fire days even after
controlling for seasonality. precip_7d_sum was tested and dropped (not
significant).

Fetches the 7-day weather history per row from data/fmi_cache/ where
available, hitting the FMI API for anything missing (slow on a first run —
expect several hours for the full dataset). Safe to interrupt and resume,
same as fetch_fmi_weather.py: every fetch is cached to disk as it goes.

Run: python scripts/build_lagged_dataset.py
"""

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from fetch_fmi_weather import fetch_daily_obs

DATA_PATH    = Path("data/training_dataset.csv")
OUTPUT_PATH  = Path("data/training_dataset_lagged.csv")
LOOKBACK_DAYS = 7
RAIN_THRESHOLD_MM = 0.1


def compute_lagged_features(fmisid: int, d) -> dict:
    """days_since_rain and temp_rolling_7d for the 7 days before date d."""
    temps = []
    days_since_rain = None
    consecutive_dry = 0
    rain_found = False

    for off in range(1, LOOKBACK_DAYS + 1):
        obs = fetch_daily_obs(fmisid, d - timedelta(days=off))
        if obs is None:
            continue
        if obs.get("temperature") is not None:
            temps.append(obs["temperature"])
        precip = obs.get("precipitation")
        if precip is not None and not rain_found:
            if precip <= RAIN_THRESHOLD_MM:
                consecutive_dry += 1
            else:
                days_since_rain = off - 1
                rain_found = True

    if not rain_found:
        days_since_rain = consecutive_dry

    return {
        "days_since_rain": days_since_rain,
        "temp_rolling_7d": sum(temps) / len(temps) if temps else None,
    }


def main() -> None:
    print("Loading dataset...", flush=True)
    df = pd.read_csv(DATA_PATH, parse_dates=["date"])
    df["date"] = df["date"].dt.date
    print(f"  {len(df)} rows", flush=True)

    print("\nBuilding lagged features (fetching missing history from FMI)...", flush=True)
    records = []
    for i, row in enumerate(df.itertuples(), 1):
        if i % 200 == 0:
            print(f"  {i}/{len(df)}", flush=True)
        records.append(compute_lagged_features(int(row.fmisid), row.date))

    lagged = pd.DataFrame(records)
    result = pd.concat([df.reset_index(drop=True), lagged], axis=1)

    n_dsr = result["days_since_rain"].notna().sum()
    n_temp = result["temp_rolling_7d"].notna().sum()
    print("\n-- Coverage ---------------------------------------------------", flush=True)
    print(f"  days_since_rain populated: {n_dsr}/{len(result)} ({n_dsr/len(result)*100:.1f}%)", flush=True)
    print(f"  temp_rolling_7d populated: {n_temp}/{len(result)} ({n_temp/len(result)*100:.1f}%)", flush=True)

    result.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved -> {OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
