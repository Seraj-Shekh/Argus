"""
Raspberry Pi gateway script.

Listens for HTTP POST from the ESP32 sensor node, enriches the payload
with wind speed and precipitation from the FMI HARMONIE forecast, then
forwards the complete reading to the Argus FastAPI backend.

Usage:
    python pi_gateway.py

Configuration: edit the CONFIG block below.
"""

import json
import math
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from pathlib import Path
from dotenv import dotenv_values

import requests

_env = dotenv_values(Path(__file__).resolve().parent.parent / ".env")

SENSOR_LAT    = float(_env["SENSOR_LAT"])
SENSOR_LON    = float(_env["SENSOR_LON"])
LOCATION_NAME = _env.get("SENSOR_LOCATION_NAME", "Sensor Node 1")
NODE_ID       = _env.get("ESP32_NODE_ID", "esp32-node-1")
LISTEN_PORT   = int(_env.get("PI_PORT", 8080))
BACKEND_URL   = _env["BACKEND_URL"]

FMI_WFS_BASE      = "https://opendata.fmi.fi/wfs"
HARMONIE_QUERY    = "fmi::forecast::harmonie::surface::point::timevaluepair"
HARMONIE_PARAMS   = "Temperature,Humidity,WindSpeedMS,Precipitation1h"
WML2_NS           = "http://www.opengis.net/waterml/2.0"
GML_NS            = "http://www.opengis.net/gml/3.2"

PARAM_MAP = {
    "Temperature":     "temperature",
    "Humidity":        "humidity",
    "WindSpeedMS":     "wind_speed",
    "Precipitation1h": "precipitation",
}


def fetch_fmi_forecast(lat: float, lon: float) -> dict | None:
    """Fetch next 24 h HARMONIE forecast and return aggregated daily values."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=24)
    try:
        r = requests.get(
            FMI_WFS_BASE,
            params={
                "service":        "WFS",
                "version":        "2.0.0",
                "request":        "GetFeature",
                "storedquery_id": HARMONIE_QUERY,
                "latlon":         f"{lat},{lon}",
                "starttime":      now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endtime":        end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "parameters":     HARMONIE_PARAMS,
            },
            timeout=15,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[fmi] Request failed: {e}")
        return None

    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as e:
        print(f"[fmi] XML parse error: {e}")
        return None

    buckets: dict[str, list[float]] = {}
    for ts in root.iter(f"{{{WML2_NS}}}MeasurementTimeseries"):
        gml_id    = ts.get(f"{{{GML_NS}}}id", "")
        param_key = gml_id.split("-")[-1]
        col       = PARAM_MAP.get(param_key)
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

    if not buckets:
        print("[fmi] No values parsed from response")
        return None

    result = {}
    for col, values in buckets.items():
        if not values:
            result[col] = None
        elif col == "precipitation":
            result[col] = round(sum(values), 2)
        else:
            result[col] = round(sum(values) / len(values), 2)
    return result


class GatewayHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, {"error": "invalid JSON"})
            return

        print(f"[esp32] Received: {payload}")

        temperature = payload.get("temperature")
        humidity    = payload.get("humidity")
        smoke       = payload.get("smoke")  # logged here but not sent to model

        if temperature is None or humidity is None:
            self._respond(400, {"error": "missing temperature or humidity"})
            return

        # Fetch wind speed and precipitation from FMI
        print(f"[fmi] Fetching forecast for {SENSOR_LAT}, {SENSOR_LON}...")
        fmi = fetch_fmi_forecast(SENSOR_LAT, SENSOR_LON)
        if fmi is None:
            self._respond(502, {"error": "FMI forecast unavailable"})
            return

        wind_speed    = fmi.get("wind_speed")    or 0.0
        precipitation = fmi.get("precipitation") or 0.0
        print(f"[fmi] wind={wind_speed} m/s  precip={precipitation} mm")

        predict_payload = {
            "node_id":       NODE_ID,
            "station_lat":   SENSOR_LAT,
            "station_lon":   SENSOR_LON,
            "location_name": LOCATION_NAME,
            "temperature":   temperature,
            "humidity":      humidity,
            "wind_speed":    wind_speed,
            "precipitation": precipitation,
            "smoke":         smoke,
        }

        print(f"[backend] POSTing to {BACKEND_URL}")
        try:
            resp   = requests.post(BACKEND_URL, json=predict_payload, timeout=20)
            result = resp.json()
            print(
                f"[backend] risk={result.get('risk_level')}  "
                f"prob={result.get('fire_risk')}  "
                f"mode={result.get('input_mode')}"
            )
            if result.get("alert"):
                print(f"[alert] {result['alert'].get('message_en', '')[:80]}")
        except Exception as e:
            print(f"[backend] Call failed: {e}")
            self._respond(502, {"error": "backend call failed"})
            return

        self._respond(200, result)

    def _respond(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):  # suppress default access log spam
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", LISTEN_PORT), GatewayHandler)
    print(f"Pi gateway running on port {LISTEN_PORT}")
    print(f"Sensor location : {SENSOR_LAT}, {SENSOR_LON}  ({LOCATION_NAME})")
    print(f"Backend URL     : {BACKEND_URL}")
    server.serve_forever()
