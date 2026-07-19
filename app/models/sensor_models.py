"""ORM models matching `db.sql` tables.

Tables:
- sensor_readings
- alerts
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func
from sqlalchemy.types import JSON

from app.database.session import Base


class SensorReading(Base):
    """SQLAlchemy model for the `sensor_readings` table."""

    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String(20), nullable=False, index=True)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    smoke = Column(Float, nullable=True)
    wind_speed = Column(Float, nullable=True)
    fwi_index = Column(Float, nullable=True)
    risk_level = Column(String(20), nullable=True)
    timestamp = Column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - trivial helper
        return f"<SensorReading(id={self.id} node_id={self.node_id})>"


class Alert(Base):
    """SQLAlchemy model for the `alerts` table."""

    __tablename__ = "alerts"

    id          = Column(Integer, primary_key=True, index=True)
    node_id     = Column(String(20), nullable=False, index=True)
    source      = Column(String(20), nullable=False, default="software")  # 'hardware' | 'software'
    message_en  = Column(Text, nullable=False)
    message_fi  = Column(Text, nullable=False)
    severity    = Column(String(20), nullable=False)
    risk_level  = Column(String(20), nullable=True)
    temperature = Column(Float, nullable=True)
    humidity    = Column(Float, nullable=True)
    wind_speed  = Column(Float, nullable=True)
    precipitation = Column(Float, nullable=True)
    smoke       = Column(Float, nullable=True)
    station_lat = Column(Float, nullable=True)
    station_lon = Column(Float, nullable=True)
    ai_metadata = Column(JSON, nullable=True)   # {model, prompt_tokens, completion_tokens, latency_ms}
    timestamp   = Column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Alert(id={self.id} node_id={self.node_id} severity={self.severity})>"