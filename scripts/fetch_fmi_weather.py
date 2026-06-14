"""
Fetch FMI hourly weather observations for fire and non-fire dates, then build
a labelled training dataset saved to data/training_dataset.csv.

Steps:
  1. Load cleaned fire events from data/fire_events_clean.csv
  2. Fetch FMI station list (cached to data/fmi_stations.json)
  3. Match each fire event to nearest station within 50 km
  4. Generate 4 non-fire dates per fire day (same station, random dates)
  5. Fetch hourly weather for all (date, station) pairs, aggregate to daily
  6. Combine into a labelled DataFrame and save

Run: python scripts/fetch_fmi_weather.py
"""

import json
import math
import random
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests


# ── Config ────────────────────────────────────────────────────────────────────

FMI_WFS_BASE      = "https://opendata.fmi.fi/wfs"
DATA_DIR          = Path(__file__).parent.parent / "data"
CACHE_DIR         = DATA_DIR / "fmi_cache"
STATIONS_CACHE    = DATA_DIR / "fmi_stations.json"
FIRE_EVENTS_CSV   = DATA_DIR / "fire_events_clean.csv"
OUTPUT_CSV        = DATA_DIR / "training_dataset.csv"
SKIPPED_LOG       = DATA_DIR / "skipped_events.log"

MAX_STATION_RADIUS_KM = 50
NON_FIRE_MULTIPLIER   = 4      # non-fire dates per unique fire (date, station) pair
REQUEST_DELAY_S       = 0.5    # pause between API calls to respect FMI rate limits
REQUEST_TIMEOUT_S     = 30
MAX_RETRIES           = 2
RANDOM_SEED           = 42
PERIOD_START          = date(2015, 1, 1)
PERIOD_END            = date.today()

# FMI hourly stored query and its parameter names
FMI_STORED_QUERY  = "fmi::observations::weather::hourly::timevaluepair"
FMI_HOURLY_PARAMS = "TA_PT1H_AVG,RH_PT1H_AVG,WS_PT1H_AVG,PRA_PT1H_ACC"

# Map from FMI param name (tail of gml:id) to output column
# Aggregation: mean for temperature/humidity/wind_speed, sum for precipitation
PARAM_MAP = {
    "TA_PT1H_AVG":  "temperature",   # °C  — daily mean of hourly averages
    "RH_PT1H_AVG":  "humidity",      # %   — daily mean of hourly averages
    "WS_PT1H_AVG":  "wind_speed",    # m/s — daily mean of hourly averages
    "PRA_PT1H_ACC": "precipitation", # mm  — daily sum of hourly accumulations
}

WML2_NS = "http://www.opengis.net/waterml/2.0"
GML_NS  = "http://www.opengis.net/gml/3.2"
EF_NS   = "http://inspire.ec.europa.eu/schemas/ef/4.0"


# ── HTTP ──────────────────────────────────────────────────────────────────────

def get_xml(params: dict) -> Optional[str]:
    """GET the FMI WFS endpoint, retry on transient failures. Returns None on permanent failure."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.get(FMI_WFS_BASE, params=params, timeout=REQUEST_TIMEOUT_S)
            r.raise_for_status()
            return r.text
        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(1.0)
    return None


# ── Distance ──────────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── FMI Stations ──────────────────────────────────────────────────────────────

def fetch_stations() -> list[dict]:
    """Return FMI station list for Finland, fetching from API and caching on first call."""
    if STATIONS_CACHE.exists():
        with open(STATIONS_CACHE) as f:
            stations = json.load(f)
        print(f"Loaded {len(stations)} FMI stations from cache")
        return stations

    print("Fetching FMI station list from API...")
    xml_text = get_xml({
        "service": "WFS", "version": "2.0.0",
        "request": "GetFeature",
        "storedquery_id": "fmi::ef::stations",
    })
    if xml_text is None:
        raise RuntimeError("Could not fetch FMI station list — check network connection")

    root = ET.fromstring(xml_text)
    stations = []

    for facility in root.iter(f"{{{EF_NS}}}EnvironmentalMonitoringFacility"):
        try:
            # fmisid is the trailing integer in the gml:identifier URL
            # e.g. "http://xml.fmi.fi/stations/101004" → 101004
            ident_el = facility.find(f"{{{GML_NS}}}identifier")
            if ident_el is None or not ident_el.text:
                continue
            parts = ident_el.text.rstrip("/").split("/")
            if not parts[-1].isdigit():
                continue
            fmisid = int(parts[-1])

            pos_el = facility.find(f".//{{{GML_NS}}}pos")
            if pos_el is None:
                continue
            coords = pos_el.text.strip().split()
            if len(coords) < 2:
                continue
            lat, lon = float(coords[0]), float(coords[1])

            if not (59.5 <= lat <= 70.1 and 19.0 <= lon <= 31.6):
                continue

            name_el = facility.find(f"{{{EF_NS}}}name")
            name = name_el.text.strip() if name_el is not None else f"station_{fmisid}"
            stations.append({"fmisid": fmisid, "name": name, "lat": lat, "lon": lon})
        except Exception:
            continue

    with open(STATIONS_CACHE, "w") as f:
        json.dump(stations, f, indent=2)
    print(f"Found and cached {len(stations)} FMI stations in Finland")
    return stations


def nearest_station(lat: float, lon: float, stations: list[dict]) -> Optional[dict]:
    """Return the nearest station within MAX_STATION_RADIUS_KM, or None if none found."""
    best, best_d = None, float("inf")
    for stn in stations:
        d = haversine_km(lat, lon, stn["lat"], stn["lon"])
        if d < best_d:
            best_d, best = d, stn
    if best_d <= MAX_STATION_RADIUS_KM:
        return {**best, "distance_km": round(best_d, 2)}
    return None


# ── FMI Observations ──────────────────────────────────────────────────────────

def _cache_path(fmisid: int, obs_date: date) -> Path:
    return CACHE_DIR / f"{fmisid}_{obs_date.isoformat()}.json"


def fetch_daily_obs(fmisid: int, obs_date: date) -> Optional[dict]:
    """
    Fetch hourly observations for one station/day, aggregate to daily values.
    Returns dict: {temperature, humidity, wind_speed, precipitation} (values may be None).
    Caches each result to disk — safe to interrupt and resume.
    Returns None only on a hard API failure (not on missing data).
    """
    cp = _cache_path(fmisid, obs_date)
    if cp.exists():
        with open(cp) as f:
            return json.load(f)

    time.sleep(REQUEST_DELAY_S)

    xml_text = get_xml({
        "service":        "WFS",
        "version":        "2.0.0",
        "request":        "GetFeature",
        "storedquery_id": FMI_STORED_QUERY,
        "fmisid":         str(fmisid),
        "starttime":      f"{obs_date.isoformat()}T00:00:00Z",
        "endtime":        f"{obs_date.isoformat()}T23:59:59Z",
        "parameters":     FMI_HOURLY_PARAMS,
    })

    if xml_text is None:
        return None

    result = _parse_hourly_xml(xml_text)

    with open(cp, "w") as f:
        json.dump(result, f)

    return result


def _parse_hourly_xml(xml_text: str) -> dict:
    """
    Parse FMI hourly WFS response. Collects all valid hourly values per parameter,
    then returns daily aggregates: mean for temp/humidity/wind, sum for precipitation.
    Handles FMI's "NaN" string and -1 sentinel for missing values.
    """
    buckets: dict[str, list[float]] = {col: [] for col in PARAM_MAP.values()}

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {col: None for col in buckets}

    for ts in root.iter(f"{{{WML2_NS}}}MeasurementTimeseries"):
        gml_id   = ts.get(f"{{{GML_NS}}}id", "")
        param_key = gml_id.split("-")[-1]   # "obs-obs-1-1-TA_PT1H_AVG" → "TA_PT1H_AVG"
        col = PARAM_MAP.get(param_key)
        if col is None:
            continue

        for tvp in ts.findall(f".//{{{WML2_NS}}}MeasurementTVP"):
            val_el = tvp.find(f"{{{WML2_NS}}}value")
            if val_el is None or not val_el.text:
                continue
            try:
                val = float(val_el.text)
            except ValueError:
                continue
            if math.isnan(val):
                continue
            # FMI uses -1 as a sentinel for precipitation "not measured"
            if col == "precipitation" and val < 0:
                continue
            buckets[col].append(val)

    result = {}
    for col, values in buckets.items():
        if not values:
            result[col] = None
        elif col == "precipitation":
            result[col] = round(sum(values), 2)
        else:
            result[col] = round(sum(values) / len(values), 2)
    return result


# ── Non-fire Date Generation ──────────────────────────────────────────────────

def make_nonfire_dates(
    global_fire_dates: set[date],
    station_fire_dates: set[date],
    n: int,
    rng: random.Random,
) -> list[date]:
    """
    Draw n random dates from PERIOD_START..PERIOD_END not present in any fire record.
    """
    excluded  = global_fire_dates | station_fire_dates
    total_days = (PERIOD_END - PERIOD_START).days
    chosen: list[date] = []
    attempts = 0
    while len(chosen) < n and attempts < n * 30:
        candidate = PERIOD_START + timedelta(days=rng.randint(0, total_days))
        if candidate not in excluded and candidate not in chosen:
            chosen.append(candidate)
        attempts += 1
    return chosen


# ── Pipeline ──────────────────────────────────────────────────────────────────

def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    CACHE_DIR.mkdir(exist_ok=True)
    rng = random.Random(RANDOM_SEED)
    log = open(SKIPPED_LOG, "w")

    # Step 1 — load fire events
    print("Loading fire events...")
    fire_df = pd.read_csv(FIRE_EVENTS_CSV, parse_dates=["date"])
    fire_df["date"] = fire_df["date"].dt.date
    print(f"  {len(fire_df)} detections, {fire_df['date'].nunique()} unique dates")

    # Step 2 — load FMI stations
    stations = fetch_stations()

    # Step 3 — match fire events to nearest station within 50 km
    print("Matching fire events to nearest FMI stations (≤50 km)...")
    matched, skipped_no_station = [], 0
    for _, row in fire_df.iterrows():
        stn = nearest_station(row["lat"], row["lon"], stations)
        if stn is None:
            skipped_no_station += 1
            log.write(f"NO_STATION  lat={row['lat']:.5f} lon={row['lon']:.5f} date={row['date']}\n")
            continue
        matched.append({
            "date":        row["date"],
            "fmisid":      stn["fmisid"],
            "station_lat": stn["lat"],
            "station_lon": stn["lon"],
            "distance_km": stn["distance_km"],
        })

    matched_df = pd.DataFrame(matched)
    print(f"  {len(matched_df)} matched, {skipped_no_station} skipped (no station within 50 km)")

    fire_pairs = matched_df.drop_duplicates(subset=["date", "fmisid"]).reset_index(drop=True)
    print(f"  {len(fire_pairs)} unique (date, station) fire pairs after deduplication")

    all_fire_dates: set[date] = set(fire_df["date"].unique())

    # Step 4 — generate non-fire dates
    print("Generating non-fire dates...")
    station_fire_dates: dict[int, set[date]] = {}
    for _, row in fire_pairs.iterrows():
        station_fire_dates.setdefault(int(row["fmisid"]), set()).add(row["date"])

    nonfire_records = []
    for fmisid, stn_fire_dates in station_fire_dates.items():
        stn_row = fire_pairs[fire_pairs["fmisid"] == fmisid].iloc[0]
        for _ in stn_fire_dates:
            for nf_date in make_nonfire_dates(all_fire_dates, stn_fire_dates, NON_FIRE_MULTIPLIER, rng):
                nonfire_records.append({
                    "date":        nf_date,
                    "fmisid":      fmisid,
                    "station_lat": stn_row["station_lat"],
                    "station_lon": stn_row["station_lon"],
                })

    nonfire_pairs = (
        pd.DataFrame(nonfire_records)
        .drop_duplicates(subset=["date", "fmisid"])
        .reset_index(drop=True)
    )
    print(f"  {len(nonfire_pairs)} unique non-fire (date, station) pairs")

    # Step 5 — fetch weather for fire days
    print(f"\nFetching weather for {len(fire_pairs)} fire day/station pairs...")
    fire_rows = []
    for i, row in fire_pairs.iterrows():
        if (i + 1) % 100 == 0:
            print(f"  Fire: {i+1}/{len(fire_pairs)}")
        obs = fetch_daily_obs(int(row["fmisid"]), row["date"])
        if obs is None:
            log.write(f"FETCH_FAIL  fmisid={row['fmisid']} date={row['date']}\n")
            continue
        fire_rows.append({**row.to_dict(), **obs, "fire": 1})

    # Step 6 — fetch weather for non-fire days
    print(f"\nFetching weather for {len(nonfire_pairs)} non-fire day/station pairs...")
    nonfire_rows = []
    for i, row in nonfire_pairs.iterrows():
        if (i + 1) % 100 == 0:
            print(f"  Non-fire: {i+1}/{len(nonfire_pairs)}")
        obs = fetch_daily_obs(int(row["fmisid"]), row["date"])
        if obs is None:
            log.write(f"FETCH_FAIL_NF fmisid={row['fmisid']} date={row['date']}\n")
            continue
        nonfire_rows.append({**row.to_dict(), **obs, "fire": 0})

    # Step 7 — combine, select columns, save
    if not fire_rows and not nonfire_rows:
        print("\nERROR: No rows collected — all API calls failed. Check network/FMI API.")
        log.close()
        return

    dataset = pd.DataFrame(fire_rows + nonfire_rows)
    dataset = dataset[["date", "fmisid", "station_lat", "station_lon",
                        "temperature", "humidity", "wind_speed", "precipitation", "fire"]]

    n_fire    = (dataset["fire"] == 1).sum()
    n_nonfire = (dataset["fire"] == 0).sum()
    n_missing = dataset[["temperature", "humidity", "wind_speed", "precipitation"]].isna().any(axis=1).sum()

    print("\n── Dataset summary ───────────────────────────────────────")
    print(f"  Total rows:                 {len(dataset)}")
    print(f"  Fire days    (label=1):     {n_fire}")
    print(f"  Non-fire days (label=0):    {n_nonfire}")
    print(f"  Rows with ≥1 missing value: {n_missing}")
    print(f"  Class ratio fire:non-fire:  1:{n_nonfire // max(n_fire, 1)}")

    dataset.to_csv(OUTPUT_CSV, index=False)
    log.close()
    print(f"\nSaved → {OUTPUT_CSV}")
    print(f"Skipped log → {SKIPPED_LOG}")


if __name__ == "__main__":
    main()
