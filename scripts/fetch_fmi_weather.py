'Builds data/training_dataset.csv by matching fire events to FMI weather stations.'

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

# config

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

# gml:id tail -> output column. temp/humidity/wind are daily means, precip is a daily sum
PARAM_MAP = {
    "TA_PT1H_AVG":  "temperature",
    "RH_PT1H_AVG":  "humidity",
    "WS_PT1H_AVG":  "wind_speed",
    "PRA_PT1H_ACC": "precipitation",
}

WML2_NS   = "http://www.opengis.net/waterml/2.0"
GML_NS    = "http://www.opengis.net/gml/3.2"
EF_NS     = "http://inspire.ec.europa.eu/schemas/ef/4.0"
XLINK_NS  = "http://www.w3.org/1999/xlink"

# fmi::ef::stations returns every station type (buoys, rain gauges, road
# sensors...). only these two networks actually answer the hourly weather query.
GOOD_NETWORKS = {
    "Automaattinen sääasema",
    "IL:n hallinnoima lentosääasema",
}


# http

def get_xml(params: dict) -> Optional[str]:
    'GET the FMI WFS endpoint, retry a couple times, give up and return None.'
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.get(FMI_WFS_BASE, params=params, timeout=REQUEST_TIMEOUT_S)
            r.raise_for_status()
            return r.text
        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(1.0)
    return None


# distance

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# FMI stations

def fetch_stations() -> list[dict]:
# Load FMI weather stations (filtered to GOOD_NETWORKS), cached after first fetch.
    if STATIONS_CACHE.exists():
        with open(STATIONS_CACHE) as f:
            stations = json.load(f)
        print(f"Loaded {len(stations)} FMI weather stations from cache", flush=True)
        return stations

    print("Fetching FMI station list from API...", flush=True)
    xml_text = get_xml({
        "service": "WFS", "version": "2.0.0",
        "request": "GetFeature",
        "storedquery_id": "fmi::ef::stations",
    })
    if xml_text is None:
        raise RuntimeError("Could not fetch FMI station list — check network connection")

    root = ET.fromstring(xml_text)
    stations = []
    skipped_network = 0

    for facility in root.iter(f"{{{EF_NS}}}EnvironmentalMonitoringFacility"):
        try:
            ident_el = facility.find(f"{{{GML_NS}}}identifier")
            if ident_el is None or not ident_el.text:
                continue
            parts = ident_el.text.rstrip("/").split("/")
            if not parts[-1].isdigit():
                continue
            fmisid = int(parts[-1])

            belongs_el = facility.find(f"{{{EF_NS}}}belongsTo")
            network = belongs_el.get(f"{{{XLINK_NS}}}title", "") if belongs_el is not None else ""
            if network not in GOOD_NETWORKS:
                skipped_network += 1
                continue

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

    print(f"  Kept {len(stations)} weather stations, skipped {skipped_network} non-weather stations", flush=True)
    with open(STATIONS_CACHE, "w") as f:
        json.dump(stations, f, indent=2)
    print(f"  Cached to {STATIONS_CACHE}", flush=True)
    return stations


def nearest_station(lat: float, lon: float, stations: list[dict]) -> Optional[dict]:
    # Nearest station within MAX_STATION_RADIUS_KM, or None
    best, best_d = None, float("inf")
    for stn in stations:
        d = haversine_km(lat, lon, stn["lat"], stn["lon"])
        if d < best_d:
            best_d, best = d, stn
    if best_d <= MAX_STATION_RADIUS_KM:
        return {**best, "distance_km": round(best_d, 2)}
    return None


# FMI observations

def _cache_path(fmisid: int, obs_date: date) -> Path:
    return CACHE_DIR / f"{fmisid}_{obs_date.isoformat()}.json"


def fetch_daily_obs(fmisid: int, obs_date: date) -> Optional[dict]:
    """
    Fetch hourly weather for one station/day and aggregate to daily values.
    Cached to disk so the script can be killed and resumed without refetching.
    Returns None only on a hard API failure, not on missing data.
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
    # Parse the WFS response and aggregate hourly values to one daily value per param.
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
            # -1 means "not measured" for precipitation
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


# non-fire date generation

def make_nonfire_dates(
    global_fire_dates: set[date],
    station_fire_dates: set[date],
    n: int,
    rng: random.Random,
) -> list[date]:
    """n random dates in range that aren't a fire date anywhere or at this station."""
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


# pipeline

def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    CACHE_DIR.mkdir(exist_ok=True)
    rng = random.Random(RANDOM_SEED)
    log = open(SKIPPED_LOG, "w")

    print("Loading fire events...", flush=True)
    fire_df = pd.read_csv(FIRE_EVENTS_CSV, parse_dates=["date"])
    fire_df["date"] = fire_df["date"].dt.date
    print(f"  {len(fire_df)} detections, {fire_df['date'].nunique()} unique dates", flush=True)

    stations = fetch_stations()

    print(f"Matching fire events to nearest station (<=50 km)...", flush=True)
    matched, skipped_no_station = [], 0
    for i, row in enumerate(fire_df.itertuples(), 1):
        if i % 3000 == 0:
            print(f"  Matching: {i}/{len(fire_df)}", flush=True)
        stn = nearest_station(row.lat, row.lon, stations)
        if stn is None:
            skipped_no_station += 1
            log.write(f"NO_STATION  lat={row.lat:.5f} lon={row.lon:.5f} date={row.date}\n")
            continue
        matched.append({
            "date":        row.date,
            "fmisid":      stn["fmisid"],
            "station_lat": stn["lat"],
            "station_lon": stn["lon"],
            "distance_km": stn["distance_km"],
        })

    matched_df = pd.DataFrame(matched)
    print(f"  {len(matched_df)} matched, {skipped_no_station} skipped (no station within 50 km)", flush=True)

    fire_pairs = matched_df.drop_duplicates(subset=["date", "fmisid"]).reset_index(drop=True)
    print(f"  {len(fire_pairs)} unique (date, station) fire pairs after deduplication", flush=True)

    all_fire_dates: set[date] = set(fire_df["date"].unique())

    print("Generating non-fire dates...", flush=True)
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
    print(f"  {len(nonfire_pairs)} unique non-fire (date, station) pairs", flush=True)

    print(f"\nFetching weather for {len(fire_pairs)} fire day/station pairs...", flush=True)
    fire_rows = []
    for i, row in enumerate(fire_pairs.itertuples(), 1):
        if i % 200 == 0:
            print(f"  Fire: {i}/{len(fire_pairs)}", flush=True)
        obs = fetch_daily_obs(int(row.fmisid), row.date)
        if obs is None:
            log.write(f"FETCH_FAIL  fmisid={row.fmisid} date={row.date}\n")
            continue
        fire_rows.append({
            "date": row.date, "fmisid": row.fmisid,
            "station_lat": row.station_lat, "station_lon": row.station_lon,
            **obs, "fire": 1,
        })

    print(f"\nFetching weather for {len(nonfire_pairs)} non-fire day/station pairs...", flush=True)
    nonfire_rows = []
    for i, row in enumerate(nonfire_pairs.itertuples(), 1):
        if i % 200 == 0:
            print(f"  Non-fire: {i}/{len(nonfire_pairs)}", flush=True)
        obs = fetch_daily_obs(int(row.fmisid), row.date)
        if obs is None:
            log.write(f"FETCH_FAIL_NF fmisid={row.fmisid} date={row.date}\n")
            continue
        nonfire_rows.append({
            "date": row.date, "fmisid": row.fmisid,
            "station_lat": row.station_lat, "station_lon": row.station_lon,
            **obs, "fire": 0,
        })

    if not fire_rows and not nonfire_rows:
        print("\nERROR: No rows collected — all API calls failed. Check network/FMI API.", flush=True)
        log.close()
        return

    dataset = pd.DataFrame(fire_rows + nonfire_rows)
    dataset = dataset[["date", "fmisid", "station_lat", "station_lon",
                        "temperature", "humidity", "wind_speed", "precipitation", "fire"]]

    weather_cols = ["temperature", "humidity", "wind_speed", "precipitation"]
    before = len(dataset)
    dataset = dataset.dropna(subset=weather_cols, how="all").reset_index(drop=True)

    n_fire     = (dataset["fire"] == 1).sum()
    n_nonfire  = (dataset["fire"] == 0).sum()
    n_missing  = dataset[weather_cols].isna().any(axis=1).sum()
    n_complete = dataset[weather_cols].notna().all(axis=1).sum()

    print("\n-- Dataset summary ------------------------------------------", flush=True)
    print(f"  Total rows (dropped {before - len(dataset)} all-empty): {len(dataset)}", flush=True)
    print(f"  Fire days         (label=1):  {n_fire}", flush=True)
    print(f"  Non-fire days     (label=0):  {n_nonfire}", flush=True)
    print(f"  Rows with >=1 missing value:  {n_missing}", flush=True)
    print(f"  Fully complete rows (all 4):  {n_complete}", flush=True)
    print(f"  Class ratio fire:non-fire:    1:{n_nonfire // max(n_fire, 1)}", flush=True)

    dataset.to_csv(OUTPUT_CSV, index=False)
    log.close()
    print(f"\nSaved -> {OUTPUT_CSV}")
    print(f"Skipped log -> {SKIPPED_LOG}")


if __name__ == "__main__":
    main()
