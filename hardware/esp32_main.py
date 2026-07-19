"""
ESP32 MicroPython firmware — Argus sensor node (pull mode).

Runs a tiny HTTP server. When the Raspberry Pi calls GET /reading,
the ESP32 reads sensors right then and returns the values as JSON.
No data is sent unless something asks for it.

Upload BOTH this file (as main.py) and esp32_config.py (as config.py)
to the ESP32 using Thonny.
"""

import dht        # MicroPython built-in
import machine    # MicroPython built-in
import network    # MicroPython built-in
import socket
import time
import ujson      # MicroPython built-in

import config

LISTEN_PORT = 80


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


def read_sensors():
    sensor = dht.DHT22(machine.Pin(config.DHT_PIN))
    sensor.measure()
    temperature = sensor.temperature()
    humidity    = sensor.humidity()
    adc  = machine.ADC(machine.Pin(config.MQ2_PIN))
    adc.atten(machine.ADC.ATTN_11DB)
    smoke = adc.read()
    return temperature, humidity, smoke


def serve():
    addr = socket.getaddrinfo("0.0.0.0", LISTEN_PORT)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(1)
    print(f"ESP32 listening on port {LISTEN_PORT}")

    while True:
        conn, addr = s.accept()
        try:
            request = conn.recv(1024).decode()
            first_line = request.split("\r\n")[0] if request else ""

            if "GET /reading" in first_line:
                try:
                    temperature, humidity, smoke = read_sensors()
                    print(f"Read: T={temperature}C H={humidity}% smoke={smoke}")
                    body = ujson.dumps({
                        "node_id":     config.NODE_ID,
                        "temperature": temperature,
                        "humidity":    humidity,
                        "smoke":       smoke,
                    })
                    response = (
                        "HTTP/1.1 200 OK\r\n"
                        "Content-Type: application/json\r\n"
                        f"Content-Length: {len(body)}\r\n"
                        "\r\n" + body
                    )
                except Exception as e:
                    body = ujson.dumps({"error": str(e)})
                    response = (
                        "HTTP/1.1 500 Internal Server Error\r\n"
                        "Content-Type: application/json\r\n"
                        f"Content-Length: {len(body)}\r\n"
                        "\r\n" + body
                    )
            else:
                body = ujson.dumps({"error": "not found"})
                response = (
                    "HTTP/1.1 404 Not Found\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "\r\n" + body
                )

            conn.send(response.encode())
        except Exception as e:
            print("Connection error:", e)
        finally:
            conn.close()


def main():
    if not connect_wifi():
        return
    serve()


main()
