"""
ESP32 MicroPython firmware — Argus sensor node.

Sensors:
  - DHT22 on GPIO 4  (temperature, humidity)
  - MQ2   on GPIO 34 (smoke / gas, ADC)

Sends a JSON POST to the Raspberry Pi gateway every SEND_INTERVAL_S seconds.

Upload BOTH this file (as main.py) and esp32_config.py (as config.py) to the
ESP32 using Thonny. Edit esp32_config.py with your WiFi credentials and Pi IP
before uploading.
"""

import dht        # MicroPython built-in
import machine    # MicroPython built-in
import network    # MicroPython built-in
import time
import ujson      # MicroPython built-in
import urequests  # MicroPython built-in

import config

PI_URL = f"http://{config.PI_HOST}:{config.PI_PORT}"


def connect_wifi() -> bool:
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    print("Connecting to WiFi...")
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    for _ in range(20):
        if wlan.isconnected():
            print("Connected:", wlan.ifconfig()[0])
            return True
        time.sleep(1)
    print("WiFi connection failed")
    return False


def read_dht22():
    sensor = dht.DHT22(machine.Pin(config.DHT_PIN))
    sensor.measure()
    return sensor.temperature(), sensor.humidity()


def read_mq2() -> int:
    adc = machine.ADC(machine.Pin(config.MQ2_PIN))
    adc.atten(machine.ADC.ATTN_11DB)   # 0–3.3 V range → 0–4095
    return adc.read()


def send_reading(temperature: float, humidity: float, smoke: int) -> None:
    payload = ujson.dumps({
        "node_id":     config.NODE_ID,
        "temperature": temperature,
        "humidity":    humidity,
        "smoke":       smoke,
    })
    try:
        resp = urequests.post(
            PI_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        risk = "?"
        try:
            risk = ujson.loads(resp.text).get("risk_level", "?")
        except Exception:
            pass
        print(f"Sent OK  risk={risk}")
        resp.close()
    except Exception as e:
        print("Send failed:", e)


def main() -> None:
    if not connect_wifi():
        return

    while True:
        try:
            temperature, humidity = read_dht22()
            smoke = read_mq2()
            print(f"T={temperature}C  H={humidity}%  smoke={smoke}")
            send_reading(temperature, humidity, smoke)
        except Exception as e:
            print("Sensor/send error:", e)
        time.sleep(config.SEND_INTERVAL_S)


main()
