"""
Raspberry Pi gateway script — pull mode.

Exposes GET /reading — when called by the backend, it:
  1. Pulls live sensor data from the ESP32 (GET http://ESP32_HOST/reading)
  2. Forwards temperature + humidity to the FastAPI backend /predict
  3. Backend handles FMI enrichment (wind speed + precipitation) — Mode B

Configuration is read from the project .env file.
Run: python hardware/pi_gateway.py
"""

import json
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
ESP32_HOST    = _env.get("ESP32_HOST", "")
ESP32_PORT    = int(_env.get("ESP32_PORT", 80))


def pull_from_esp32() -> dict | None:
    if not ESP32_HOST:
        print("[esp32] ESP32_HOST not configured")
        return None
    url = f"http://{ESP32_HOST}:{ESP32_PORT}/reading"
    print(f"[esp32] Pulling from {url}")
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[esp32] Pull failed: {e}")
        return None


def do_reading() -> tuple[dict | None, str | None]:
    """Pull from ESP32, forward to backend. Wind + precip fetched by backend (Mode B)."""
    sensor = pull_from_esp32()
    if sensor is None:
        return None, "Could not reach ESP32"

    temperature = sensor.get("temperature")
    humidity    = sensor.get("humidity")
    smoke       = sensor.get("smoke")
    print(f"[esp32] T={temperature}C H={humidity}% smoke={smoke}")

    if temperature is None or humidity is None:
        return None, "ESP32 returned incomplete data"

    # Send only what the hardware provides — backend fetches wind + precip from FMI (Mode B)
    predict_payload = {
        "node_id":       NODE_ID,
        "station_lat":   SENSOR_LAT,
        "station_lon":   SENSOR_LON,
        "location_name": LOCATION_NAME,
        "temperature":   temperature,
        "humidity":      humidity,
        "smoke":         smoke,
    }

    print(f"[backend] POSTing to {BACKEND_URL} (Mode B — FMI handles wind + precip)")
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
        return result, None
    except Exception as e:
        return None, f"Backend call failed: {e}"


class GatewayHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/reading":
            result, error = do_reading()
            if error:
                self._respond(502, {"error": error})
            else:
                self._respond(200, result)
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", LISTEN_PORT), GatewayHandler)
    print(f"Pi gateway running on port {LISTEN_PORT}")
    print(f"Sensor location : {SENSOR_LAT}, {SENSOR_LON}  ({LOCATION_NAME})")
    print(f"ESP32 host      : {ESP32_HOST}:{ESP32_PORT}")
    print(f"Backend URL     : {BACKEND_URL}")
    server.serve_forever()
