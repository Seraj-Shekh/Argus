"""Fire risk prediction endpoint backed by the trained Random Forest model.

Supports three input modes, detected from which fields are present in the
request body:

- Mode A (fmi_only):   only station_lat/station_lon given, all weather
                        values are fetched from FMI. No hardware needed.
- Mode B (hardware_fmi): temperature/humidity/wind_speed given by the caller
                        (e.g. an ESP32 node), precipitation enriched from FMI.
- Mode C (hardware_only): temperature/humidity/wind_speed/precipitation all
                        given by the caller, no FMI calls are made at all.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.sensor_models import SensorReading
from app.utils.fmi_client import (
    fetch_forecast_weather,
    fetch_forecast_precipitation,
    fetch_lagged_features,
)

router = APIRouter()

BASE_FEATURES = [
    "temperature", "humidity", "wind_speed", "precipitation",
    "station_lat", "station_lon", "day_of_year", "month",
]
LAGGED_FEATURES = ["days_since_rain", "temp_rolling_7d"]

_model = None


def set_model(model) -> None:
    """Set the loaded model singleton. Called once from main.py on startup."""
    global _model
    _model = model


def get_model():
    if _model is None:
        raise HTTPException(
            status_code=500,
            detail="Fire risk model is not loaded — check application startup logs",
        )
    return _model


class PredictRequest(BaseModel):
    station_lat: float
    station_lon: float
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    wind_speed: Optional[float] = None
    precipitation: Optional[float] = None
    timestamp: Optional[str] = Field(
        default=None, description="ISO8601 timestamp, defaults to current UTC time"
    )


class PredictResponse(BaseModel):
    fire_risk: float
    risk_level: str
    confidence: float
    input_mode: str
    fmi_precipitation: Optional[float]
    fmi_station_name: Optional[str]
    distance_to_station_km: Optional[float]
    timestamp: str
    features_used: dict
    warning: Optional[str] = None


def _risk_level(probability: float) -> str:
    if probability < 0.3:
        return "low"
    if probability < 0.6:
        return "medium"
    return "high"


def _detect_mode(body: PredictRequest) -> str:
    """
    Decide which of the three input modes a request belongs to, based on
    which sensor fields were provided. temperature/humidity/wind_speed must
    be given together or not at all — a partial set is rejected.
    """
    sensor_fields = (body.temperature, body.humidity, body.wind_speed)
    if all(v is None for v in sensor_fields):
        return "fmi_only"
    if any(v is None for v in sensor_fields):
        raise HTTPException(
            status_code=422,
            detail="temperature, humidity and wind_speed must all be provided "
            "together, or all omitted to use FMI-only mode",
        )
    return "hardware_only" if body.precipitation is not None else "hardware_fmi"


@router.get("/sensor-readings")
def get_sensor_readings(db: Session = Depends(get_db)):
    rows = db.query(SensorReading).order_by(SensorReading.timestamp.desc()).limit(200).all()
    return [
        {
            "id": r.id,
            "node_id": r.node_id,
            "temperature": r.temperature,
            "humidity": r.humidity,
            "wind_speed": r.wind_speed,
            "risk_level": r.risk_level,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rows
    ]


@router.post("/predict", response_model=PredictResponse)
def predict(body: PredictRequest, db: Session = Depends(get_db)) -> PredictResponse:
    model = get_model()

    if body.timestamp:
        try:
            ts = datetime.fromisoformat(body.timestamp.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="timestamp must be ISO8601")
    else:
        ts = datetime.now(timezone.utc)

    mode = _detect_mode(body)
    warning = None
    fmi_precipitation = None
    fmi_station_name = None
    distance_km = None

    if mode == "fmi_only":
        weather = fetch_forecast_weather(body.station_lat, body.station_lon)
        temperature = weather["temperature"]
        humidity = weather["humidity"]
        wind_speed = weather["wind_speed"]
        precipitation = weather["precipitation"]
        fmi_precipitation = precipitation
        fmi_station_name = "FMI HARMONIE forecast"
        distance_km = None
        warning = weather.get("error")

    elif mode == "hardware_fmi":
        temperature, humidity, wind_speed = body.temperature, body.humidity, body.wind_speed
        precip_info = fetch_forecast_precipitation(body.station_lat, body.station_lon)
        precipitation = precip_info.get("precipitation_mm")
        fmi_precipitation = precipitation
        fmi_station_name = "FMI HARMONIE forecast"
        distance_km = None
        warning = precip_info.get("error")

    else:  # hardware_only — no FMI calls at all
        temperature, humidity, wind_speed = body.temperature, body.humidity, body.wind_speed
        precipitation = body.precipitation

    features = {
        "temperature": temperature,
        "humidity": humidity,
        "wind_speed": wind_speed,
        "precipitation": precipitation,
        "station_lat": body.station_lat,
        "station_lon": body.station_lon,
        "day_of_year": ts.timetuple().tm_yday,
        "month": ts.month,
    }

    # If the loaded model was retrained with lagged features (10 features),
    # compute them. The imputer handles None if data is unavailable.
    feature_order = BASE_FEATURES
    if model.n_features_in_ == len(BASE_FEATURES) + len(LAGGED_FEATURES):
        lagged = fetch_lagged_features(body.station_lat, body.station_lon)
        features.update(lagged)
        feature_order = BASE_FEATURES + LAGGED_FEATURES

    X = pd.DataFrame([features], columns=feature_order)
    proba = model.predict_proba(X)[0]
    fire_proba = float(proba[1])
    confidence = float(max(proba))
    risk_level = _risk_level(fire_proba)

    try:
        # sensor_readings has no precipitation/lat/lon/input_mode columns yet,
        # so only the fields that exist on the model are logged.
        db.add(SensorReading(
            node_id="predict-api",
            temperature=temperature,
            humidity=humidity,
            wind_speed=wind_speed,
            risk_level=risk_level,
        ))
        db.commit()
    except Exception:
        db.rollback()

    return PredictResponse(
        fire_risk=round(fire_proba, 4),
        risk_level=risk_level,
        confidence=round(confidence, 4),
        input_mode=mode,
        fmi_precipitation=fmi_precipitation,
        fmi_station_name=fmi_station_name,
        distance_to_station_km=distance_km,
        timestamp=ts.isoformat(),
        features_used=features,
        warning=warning,
    )
