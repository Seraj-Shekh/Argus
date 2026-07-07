"""
Checks whether lagged weather features (days since rain, 7-day rolling
temperature, 7-day precipitation sum) actually separate fire days from
non-fire days in data/training_dataset.csv, before adding them to the model.

Runs on a stratified random sample (500 fire / 500 non-fire rows) rather than
the full dataset — most of the 7-day lookback history isn't in
data/fmi_cache/ yet, and fetching all of it from FMI would take hours. The
sample is large enough for the statistical tests to be meaningful.

Run: python scripts/analyze_lagged_features.py
"""

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
from fetch_fmi_weather import fetch_daily_obs  # reuses caching + retry logic

DATA_PATH    = Path("data/training_dataset.csv")
OUTPUT_DIR   = Path("data/analysis")
LOOKBACK_DAYS = 7
SAMPLE_PER_CLASS = 500
RANDOM_SEED  = 42
RAIN_THRESHOLD_MM = 0.1  # a day counts as "dry" if precipitation <= this


def build_history(sample: pd.DataFrame) -> dict:
    """Fetch (or load from cache) the prior LOOKBACK_DAYS of weather for every
    row in the sample. Returns {(fmisid, date): obs_dict}."""
    history: dict = {}
    pairs = set()
    for fmisid, d in zip(sample["fmisid"], sample["date"]):
        for off in range(1, LOOKBACK_DAYS + 1):
            pairs.add((int(fmisid), d - timedelta(days=off)))

    print(f"Fetching {len(pairs)} (station, date) lookback pairs...", flush=True)
    for i, (fmisid, d) in enumerate(sorted(pairs), 1):
        if i % 500 == 0:
            print(f"  {i}/{len(pairs)}", flush=True)
        history[(fmisid, d)] = fetch_daily_obs(fmisid, d)
    return history


def compute_lagged_features(row, history: dict) -> dict:
    """days_since_rain, temp_rolling_7d, precip_7d_sum, consecutive_dry_days
    for the 7 days before row['date'] at row['fmisid']."""
    fmisid, d = int(row["fmisid"]), row["date"]

    temps, precips = [], []
    days_since_rain = None
    consecutive_dry = 0
    rain_found = False

    for off in range(1, LOOKBACK_DAYS + 1):
        obs = history.get((fmisid, d - timedelta(days=off)))
        if obs is None:
            continue
        if obs.get("temperature") is not None:
            temps.append(obs["temperature"])
        precip = obs.get("precipitation")
        if precip is not None:
            precips.append(precip)
            is_dry = precip <= RAIN_THRESHOLD_MM
            if not rain_found:
                if is_dry:
                    consecutive_dry += 1
                else:
                    days_since_rain = off - 1
                    rain_found = True

    if not rain_found:
        days_since_rain = consecutive_dry  # rained 0 times in window, or all data missing

    return {
        "days_since_rain":     days_since_rain,
        "temp_rolling_7d":     sum(temps) / len(temps) if temps else None,
        "precip_7d_sum":       sum(precips) if precips else None,
        "consecutive_dry_days": consecutive_dry,
    }


def run_tests(df: pd.DataFrame, metric: str) -> dict:
    fire_vals    = df.loc[df["fire"] == 1, metric].dropna()
    nonfire_vals = df.loc[df["fire"] == 0, metric].dropna()

    t_stat, t_p = stats.ttest_ind(fire_vals, nonfire_vals, equal_var=False)
    u_stat, u_p = stats.mannwhitneyu(fire_vals, nonfire_vals, alternative="two-sided")

    return {
        "metric": metric,
        "fire_mean": fire_vals.mean(), "fire_n": len(fire_vals),
        "nonfire_mean": nonfire_vals.mean(), "nonfire_n": len(nonfire_vals),
        "t_stat": t_stat, "t_p": t_p,
        "u_stat": u_stat, "u_p": u_p,
        "significant": t_p < 0.05 and u_p < 0.05,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading dataset...", flush=True)
    df = pd.read_csv(DATA_PATH, parse_dates=["date"])
    df["date"] = df["date"].dt.date

    fire = df[df["fire"] == 1].sample(n=SAMPLE_PER_CLASS, random_state=RANDOM_SEED)

    # Month-matched non-fire sample: fire days cluster in summer, so a plain
    # random non-fire sample is mostly winter and confounds every lagged
    # metric with seasonality. Sample non-fire rows from the same months,
    # in the same proportions, as the fire sample.
    nonfire_pool = df[df["fire"] == 0].copy()
    nonfire_pool["month"] = [d.month for d in nonfire_pool["date"]]
    fire_months = [d.month for d in fire["date"]]

    nonfire_parts = []
    rng_state = RANDOM_SEED
    for month, count in pd.Series(fire_months).value_counts().items():
        pool = nonfire_pool[nonfire_pool["month"] == month]
        nonfire_parts.append(pool.sample(n=count, random_state=rng_state, replace=len(pool) < count))
        rng_state += 1
    nonfire = pd.concat(nonfire_parts).drop(columns="month")

    sample = pd.concat([fire, nonfire]).reset_index(drop=True)
    print(f"  Sampled {len(sample)} rows ({len(fire)} fire / {len(nonfire)} non-fire, "
          f"non-fire month-matched to fire)", flush=True)

    history = build_history(sample)

    print("\nComputing lagged features...", flush=True)
    lagged = sample.apply(lambda row: compute_lagged_features(row, history), axis=1, result_type="expand")
    result = pd.concat([sample.reset_index(drop=True), lagged], axis=1)

    metrics = ["days_since_rain", "temp_rolling_7d", "precip_7d_sum", "consecutive_dry_days"]

    print("\n-- Group means --------------------------------------------", flush=True)
    test_results = []
    for metric in metrics:
        r = run_tests(result, metric)
        test_results.append(r)
        print(f"  {metric}:", flush=True)
        print(f"    fire    mean = {r['fire_mean']:.3f}  (n={r['fire_n']})", flush=True)
        print(f"    nonfire mean = {r['nonfire_mean']:.3f}  (n={r['nonfire_n']})", flush=True)
        print(f"    t-test  p = {r['t_p']:.4g}   Mann-Whitney p = {r['u_p']:.4g}"
              f"   significant={r['significant']}", flush=True)

    result.to_csv(OUTPUT_DIR / "lagged_features_sample.csv", index=False)

    # box plot: days_since_rain fire vs non-fire
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.boxplot(
        [result.loc[result["fire"] == 1, "days_since_rain"].dropna(),
         result.loc[result["fire"] == 0, "days_since_rain"].dropna()],
        tick_labels=["fire", "non-fire"],
    )
    ax.set_ylabel("days since last rain")
    ax.set_title("Days since rain: fire vs non-fire")
    fig.savefig(OUTPUT_DIR / "days_since_rain_boxplot.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    # distribution: consecutive dry days, fire days only
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.hist(result.loc[result["fire"] == 1, "consecutive_dry_days"].dropna(), bins=8)
    ax.set_xlabel("consecutive dry days")
    ax.set_ylabel("count")
    ax.set_title("Consecutive dry days on fire days")
    fig.savefig(OUTPUT_DIR / "consecutive_dry_days_hist.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"\nPlots saved to {OUTPUT_DIR}/", flush=True)

    print("\n-- Conclusion -----------------------------------------------", flush=True)
    any_significant = any(r["significant"] for r in test_results)
    if any_significant:
        sig_metrics = [r["metric"] for r in test_results if r["significant"]]
        print(f"  Significant difference found for: {', '.join(sig_metrics)}", flush=True)
        print("  -> Lagged features differentiate fire from non-fire days. Add them to the model.", flush=True)
    else:
        print("  No metric showed a significant difference between fire and non-fire days.", flush=True)
        print("  -> The current 8-feature model likely already captures this signal adequately.", flush=True)


if __name__ == "__main__":
    main()
