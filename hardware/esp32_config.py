"""
Generates config.py for the ESP32 from the project .env file.

Run this on your PC whenever .env changes, then upload the generated
config.py to the ESP32 using Thonny.

    python hardware/esp32_config.py
"""

from pathlib import Path
from dotenv import dotenv_values

ENV_PATH    = Path(__file__).resolve().parent.parent / ".env"
OUTPUT_PATH = Path(__file__).resolve().parent / "config.py"


def main() -> None:
    env = dotenv_values(ENV_PATH)

    missing = [k for k in (
        "WIFI_SSID", "WIFI_PASSWORD", "PI_HOST", "PI_PORT",
        "ESP32_NODE_ID", "ESP32_DHT_PIN", "ESP32_MQ2_PIN", "ESP32_SEND_INTERVAL_S",
    ) if not env.get(k)]
    if missing:
        print(f"Missing keys in .env: {', '.join(missing)}")
        return

    content = f"""\
# Auto-generated from .env — do not edit manually.
# Upload this file to the ESP32 as config.py using Thonny.

WIFI_SSID       = {env['WIFI_SSID']!r}
WIFI_PASSWORD   = {env['WIFI_PASSWORD']!r}
PI_HOST         = {env['PI_HOST']!r}
PI_PORT         = {int(env['PI_PORT'])}
NODE_ID         = {env['ESP32_NODE_ID']!r}
DHT_PIN         = {int(env['ESP32_DHT_PIN'])}
MQ2_PIN         = {int(env['ESP32_MQ2_PIN'])}
SEND_INTERVAL_S = {int(env['ESP32_SEND_INTERVAL_S'])}
"""

    OUTPUT_PATH.write_text(content)
    print(f"Generated {OUTPUT_PATH}")
    print(f"  SSID     : {env['WIFI_SSID']}")
    print(f"  PI_HOST  : {env['PI_HOST']}:{env['PI_PORT']}")
    print(f"  NODE_ID  : {env['ESP32_NODE_ID']}")


if __name__ == "__main__":
    main()
