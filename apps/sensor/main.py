import http.client
import json
import math
import os
import random
import socket
import time

import paho.mqtt.client as mqtt

MQTT_CENTRAL_HOST = os.getenv("MQTT_HOST", "mqtt-central")
MQTT_CENTRAL_PORT = int(os.getenv("MQTT_PORT", "1883"))


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("localhost")

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect("/var/run/docker.sock")


def _container_name() -> str:
    container_id = open("/etc/hostname").read().strip()
    conn = _UnixHTTPConnection()
    conn.request("GET", f"/containers/{container_id}/json")
    data = json.loads(conn.getresponse().read())
    return data["Name"].lstrip("/")


def _compute_gps(station_id: int) -> tuple[float, float]:
    seed = int(os.getenv("SIM_RANDOM_SEED", "42")) + station_id
    rng = random.Random(seed)
    origin_lat = float(os.getenv("SIM_AREA_SW_LAT", "40.630"))
    origin_lng = float(os.getenv("SIM_AREA_SW_LNG", "-8.660"))
    width_m = float(os.getenv("SIM_AREA_WIDTH_M", "1000"))
    height_m = float(os.getenv("SIM_AREA_HEIGHT_M", "1000"))
    lat = origin_lat + rng.uniform(0.05, 0.95) * height_m / 111000
    lng = origin_lng + rng.uniform(0.05, 0.95) * width_m / (111000 * math.cos(math.radians(origin_lat)))
    return round(lat, 6), round(lng, 6)


def _own_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


container_name = _container_name()
index = int(container_name.rsplit("-", 1)[-1])
SENSOR_ID = 20 + index
SENSOR_MAC = f"6e:06:e0:03:01:{index:02x}"
SENSOR_LAT, SENSOR_LNG = _compute_gps(SENSOR_ID)

_payload = {
    "sensor_id":   SENSOR_ID,
    "temperature": round(random.uniform(15.0, 35.0), 2),
    "humidity":    round(random.uniform(30.0, 90.0), 2),
    "co2":         round(random.uniform(400.0, 2000.0), 2),
    "lat":         SENSOR_LAT,
    "lng":         SENSOR_LNG,
    "timestamp":   time.time(),
}


def _announce(ip: str):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sensor-announce-{SENSOR_ID}")
    c.connect(MQTT_CENTRAL_HOST, MQTT_CENTRAL_PORT)
    c.publish("sim/announce", json.dumps({
        "station_id":     SENSOR_ID,
        "mac":            SENSOR_MAC,
        "container_name": container_name,
        "ip":             ip,
        "lat":            SENSOR_LAT,
        "lng":            SENSOR_LNG,
        "entity_type":    "sensor",
    }))
    c.disconnect()


def _on_connect(client, userdata, flags, reason_code, properties):
    print(f"Sensor {SENSOR_ID} connected: {reason_code}", flush=True)
    client.subscribe("sensor/request_data")


def _on_message(client, userdata, msg):
    client.publish("sensor/data_response", json.dumps(_payload))
    print(f"Sensor {SENSOR_ID} responded to request", flush=True)


ip = _own_ip()
_announce(ip)
print(f"Sensor {SENSOR_ID} announced at {ip} ({SENSOR_LAT}, {SENSOR_LNG})", flush=True)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sensor-{SENSOR_ID}")
client.on_connect = _on_connect
client.on_message = _on_message
client.connect(MQTT_CENTRAL_HOST, MQTT_CENTRAL_PORT)
client.loop_forever()
