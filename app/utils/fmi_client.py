"""FMI client for the /predict endpoint.

Observations (fetch_fmi_weather / fetch_precipitation_for_location) are kept
for reference but predictions now use the 24-hour HARMONIE forecast so the
input matches the 24-hour daily aggregates the model was trained on.
"""
from __future__ import annotations

import json
import math
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

from app.config.settings import settings

DATA_DIR       = Path(__file__).resolve().parent.parent.parent / "data"
STATIONS_CACHE = DATA_DIR / "fmi_stations.json"

MAX_STATION_RADIUS_KM = 50
REQUEST_TIMEOUT_S     = 15
CACHE_TTL_S           = 3600   # 1 hour

GML_NS  = "http://www.opengis.net/gml/3.2"
WML2_NS = "http://www.opengis.net/waterml/2.0"

# --- observation parameters (used by training scripts, kept for reference) ---
OBS_PARAM_MAP = {
    "TA_PT1H_AVG":  "temperature",
    "RH_PT1H_AVG":  "humidity",
    "WS_PT1H_AVG":  "wind_speed",
    "PRA_PT1H_ACC": "precipitation",
}

# --- HARMONIE forecast parameters ---
FORECAST_PARAM_MAP = {
    "Temperature":    "temperature",
    "Humidity":       "humidity",
    "WindSpeedMS":    "wind_speed",
    "Precipitation1h": "precipitation",
}
FORECAST_STORED_QUERY = "fmi::forecast::harmonie::surface::point::timevaluepair"
FORECAST_PARAMETERS   = "Temperature,Humidity,WindSpeedMS,Precipitation1h"

# in-memory caches keyed by (rounded_lat, rounded_lon)
_forecast_cache: dict[tuple[float, float], tuple[float, dict]] = {}
_precip_forecast_cache: dict[tuple[float, float], tuple[float, dict]] = {}

# observation cache (kept for training-script compatibility)
_weather_cache: dict[tuple[float, float], tuple[float, dict]] = {}
_precip_cache:  dict[tuple[float, float], tuple[float, dict]] = {}
_stations_cache: Optional[list[dict]] = None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _load_stations() -> list[dict]:
    global _stations_cache
    if _stations_cache is not None:
        return _stations_cache
    if not STATIONS_CACHE.exists():
        raise RuntimeError(
            f"{STATIONS_CACHE} not found — run scripts/fetch_fmi_weather.py first"
        )
    with open(STATIONS_CACHE) as f:
        _stations_cache = json.load(f)
    return _stations_cache


def _nearest_station(lat, lon) -> Optional[dict]:
    stations = _load_stations()
    best, best_d = None, float("inf")
    for stn in stations:
        d = _haversine_km(lat, lon, stn["lat"], stn["lon"])
        if d < best_d:
            best_d, best = d, stn
    if best is not None and best_d <= MAX_STATION_RADIUS_KM:
        return {**best, "distance_km": round(best_d, 2)}
    return None


def _parse_wml2_buckets(xml_text: str, param_map: dict) -> Optional[dict[str, list[float]]]:
    """Parse a WML2 GetFeature response into {column: [values]} using the given param_map."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    buckets: dict[str, list[float]] = {}
    for ts in root.iter(f"{{{WML2_NS}}}MeasurementTimeseries"):
        gml_id = ts.get(f"{{{GML_NS}}}id", "")
        param_key = gml_id.split("-")[-1]
        col = param_map.get(param_key)
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
            if col == "precipitation" and val < 0:
                continue
            buckets.setdefault(col, []).append(val)
    return buckets


def _aggregate(buckets: dict[str, list[float]]) -> dict[str, Optional[float]]:
    """Mean for temp/humidity/wind, sum for precipitation."""
    result: dict[str, Optional[float]] = {
        "temperature": None, "humidity": None,
        "wind_speed": None,  "precipitation": None,
    }
    for col, values in buckets.items():
        if not values:
            continue
        result[col] = round(sum(values), 2) if col == "precipitation" \
                      else round(sum(values) / len(values), 2)
    return result


# ---------------------------------------------------------------------------
# HARMONIE 24-hour forecast (used by /predict)
# ---------------------------------------------------------------------------

def _fetch_harmonie(lat: float, lon: float) -> Optional[dict[str, list[float]]]:
    """Fetch the next 24 h of HARMONIE forecast for any lat/lon."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=24)
    try:
        r = requests.get(
            settings.fmi_base_url,
            params={
                "service":          "WFS",
                "version":          "2.0.0",
                "request":          "GetFeature",
                "storedquery_id":   FORECAST_STORED_QUERY,
                "latlon":           f"{lat},{lon}",
                "starttime":        now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endtime":          end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "parameters":       FORECAST_PARAMETERS,
            },
            timeout=REQUEST_TIMEOUT_S,
        )
        r.raise_for_status()
    except requests.RequestException:
        return None
    return _parse_wml2_buckets(r.text, FORECAST_PARAM_MAP)


def fetch_forecast_weather(lat: float, lon: float) -> dict:
    """
    Return the 24-hour HARMONIE forecast for (lat, lon) aggregated to a
    single daily value — the same aggregation used when building the training
    dataset. Cached in memory for CACHE_TTL_S seconds.

    Returns:
        {temperature, humidity, wind_speed, precipitation}  — any may be None
        plus an optional "error" key if the forecast call failed.
    """
    cache_key = (round(lat, 3), round(lon, 3))
    cached = _forecast_cache.get(cache_key)
    if cached and time.time() - cached[0] < CACHE_TTL_S:
        return cached[1]

    buckets = _fetch_harmonie(lat, lon)
    if buckets is None:
        result = {
            "temperature": None, "humidity": None,
            "wind_speed": None,  "precipitation": None,
            "error": "FMI HARMONIE forecast request failed",
        }
        _forecast_cache[cache_key] = (time.time(), result)
        return result

    result = _aggregate(buckets)
    if all(result[c] is None for c in ("temperature", "humidity", "wind_speed", "precipitation")):
        result["error"] = "FMI HARMONIE returned no values for this location"

    _forecast_cache[cache_key] = (time.time(), result)
    return result


def fetch_forecast_precipitation(lat: float, lon: float) -> dict:
    """
    24-hour forecast precipitation only — used for Mode B (hardware sensor
    provides temp/humidity/wind, FMI supplements precipitation).
    Cached separately from the full forecast.
    """
    cache_key = (round(lat, 3), round(lon, 3))
    cached = _precip_forecast_cache.get(cache_key)
    if cached and time.time() - cached[0] < CACHE_TTL_S:
        return cached[1]

    buckets = _fetch_harmonie(lat, lon)
    precip_vals = (buckets or {}).get("precipitation", [])
    precipitation = round(sum(precip_vals), 2) if precip_vals else None

    result = {"precipitation_mm": precipitation}
    if precipitation is None:
        result["error"] = "FMI HARMONIE forecast failed or returned no precipitation data"

    _precip_forecast_cache[cache_key] = (time.time(), result)
    return result


# ---------------------------------------------------------------------------
# Lagged features for prediction (days_since_rain, temp_rolling_7d)
# ---------------------------------------------------------------------------

RAIN_THRESHOLD_MM = 0.1
LOOKBACK_DAYS     = 7
_lagged_cache: dict[tuple[float, float], tuple[float, dict]] = {}


def _fetch_historical_daily(fmisid: int, date_obj) -> Optional[dict]:
    """
    Return aggregated daily observations for one (fmisid, date) pair.
    Reads from the file-based cache built by the training scripts first —
    most historical dates are already there, so this is usually instant.
    Falls back to a live FMI API call for anything missing.
    """
    cache_file = DATA_DIR / "fmi_cache" / f"{fmisid}_{date_obj.isoformat()}.json"
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # Not cached — fetch from FMI
    try:
        r = requests.get(
            settings.fmi_base_url,
            params={
                "service":        "WFS",
                "version":        "2.0.0",
                "request":        "GetFeature",
                "storedquery_id": "fmi::observations::weather::hourly::timevaluepair",
                "fmisid":         str(fmisid),
                "starttime":      f"{date_obj.isoformat()}T00:00:00Z",
                "endtime":        f"{date_obj.isoformat()}T23:59:59Z",
                "parameters":     "TA_PT1H_AVG,RH_PT1H_AVG,WS_PT1H_AVG,PRA_PT1H_ACC",
            },
            timeout=REQUEST_TIMEOUT_S,
        )
        r.raise_for_status()
    except requests.RequestException:
        return None

    buckets = _parse_wml2_buckets(r.text, OBS_PARAM_MAP)
    if buckets is None:
        return None
    result = _aggregate(buckets)

    # Write to file cache so future calls skip the network
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(result, f)
    except OSError:
        pass

    return result


def fetch_lagged_features(lat: float, lon: float) -> dict:
    """
    Compute days_since_rain and temp_rolling_7d for the 7 days ending
    yesterday at the nearest FMI station to (lat, lon).

    Returns:
        {"days_since_rain": int|None, "temp_rolling_7d": float|None}
        Both may be None if data is unavailable.
    """
    cache_key = (round(lat, 3), round(lon, 3))
    cached = _lagged_cache.get(cache_key)
    if cached and time.time() - cached[0] < CACHE_TTL_S:
        return cached[1]

    station = _nearest_station(lat, lon)
    if station is None:
        result = {"days_since_rain": None, "temp_rolling_7d": None}
        _lagged_cache[cache_key] = (time.time(), result)
        return result

    from datetime import date, timedelta
    today = date.today()
    temps = []
    days_since_rain = None
    consecutive_dry = 0
    rain_found = False

    for off in range(1, LOOKBACK_DAYS + 1):
        obs = _fetch_historical_daily(station["fmisid"], today - timedelta(days=off))
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

    result = {
        "days_since_rain": days_since_rain,
        "temp_rolling_7d": round(sum(temps) / len(temps), 2) if temps else None,
    }
    _lagged_cache[cache_key] = (time.time(), result)
    return result


# ---------------------------------------------------------------------------
# Observation-based functions (kept for training scripts)
# ---------------------------------------------------------------------------

def _fetch_today_observations(fmisid: int, parameters: str) -> Optional[dict[str, list[float]]]:
    from datetime import date
    today = date.today()
    try:
        r = requests.get(
            settings.fmi_base_url,
            params={
                "service":          "WFS",
                "version":          "2.0.0",
                "request":          "GetFeature",
                "storedquery_id":   "fmi::observations::weather::hourly::timevaluepair",
                "fmisid":           str(fmisid),
                "starttime":        f"{today.isoformat()}T00:00:00Z",
                "endtime":          f"{today.isoformat()}T23:59:59Z",
                "parameters":       parameters,
            },
            timeout=REQUEST_TIMEOUT_S,
        )
        r.raise_for_status()
    except requests.RequestException:
        return None
    return _parse_wml2_buckets(r.text, OBS_PARAM_MAP)


def fetch_precipitation_for_location(lat: float, lon: float) -> dict:
    """Observation-based precipitation (kept for backwards compatibility)."""
    cache_key = (round(lat, 3), round(lon, 3))
    cached = _precip_cache.get(cache_key)
    if cached and time.time() - cached[0] < CACHE_TTL_S:
        return cached[1]

    station = _nearest_station(lat, lon)
    if station is None:
        result = {"precipitation_mm": None, "error": "no station within 50km"}
        _precip_cache[cache_key] = (time.time(), result)
        return result

    buckets = _fetch_today_observations(station["fmisid"], "PRA_PT1H_ACC")
    values  = (buckets or {}).get("precipitation", [])
    precipitation_mm = round(sum(values), 2) if values else None

    result = {
        "station_id":      station["fmisid"],
        "station_name":    station["name"],
        "precipitation_mm": precipitation_mm,
        "distance_km":     station["distance_km"],
    }
    if precipitation_mm is None:
        result["error"] = "FMI request failed or returned no data"

    _precip_cache[cache_key] = (time.time(), result)
    return result


def fetch_fmi_weather(lat: float, lon: float) -> dict:
    """Observation-based full weather (kept for backwards compatibility)."""
    cache_key = (round(lat, 3), round(lon, 3))
    cached = _weather_cache.get(cache_key)
    if cached and time.time() - cached[0] < CACHE_TTL_S:
        return cached[1]

    station = _nearest_station(lat, lon)
    if station is None:
        result = {
            "temperature": None, "humidity": None,
            "wind_speed": None,  "precipitation": None,
            "error": "no station within 50km",
        }
        _weather_cache[cache_key] = (time.time(), result)
        return result

    buckets = _fetch_today_observations(
        station["fmisid"], "TA_PT1H_AVG,RH_PT1H_AVG,WS_PT1H_AVG,PRA_PT1H_ACC"
    )
    result = {
        "station_id":   station["fmisid"],
        "station_name": station["name"],
        "distance_km":  station["distance_km"],
        **_aggregate(buckets or {}),
    }
    if all(result[c] is None for c in ("temperature", "humidity", "wind_speed", "precipitation")):
        result["error"] = "FMI returned no observations for this station today"

    _weather_cache[cache_key] = (time.time(), result)
    return result
