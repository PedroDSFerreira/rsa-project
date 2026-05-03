import json
import os
import socket
import time
from enum import Enum, auto

import paho.mqtt.client as mqtt

from vanetza_client import VanetzaClient

DRONE_ID = int(os.environ["VANETZA_STATION_ID"])
DRONE_LAT = float(os.environ["VANETZA_LATITUDE"])
DRONE_LNG = float(os.environ["VANETZA_LONGITUDE"])
DRONE_MAC = os.environ["VANETZA_MAC_ADDRESS"]
CONTAINER_NAME = os.environ["DRONE_CONTAINER_NAME"]

MQTT_CENTRAL_HOST = os.getenv("MQTT_HOST", "mqtt-central")
MQTT_CENTRAL_PORT = int(os.getenv("MQTT_PORT", "1883"))
TICK_MS = int(os.getenv("TICK_REAL_MS", "500"))
DRONE_SPEED = float(os.getenv("DRONE_SPEED_M_S", "5.0"))


class State(Enum):
    IDLE = auto()
    EXPLORING = auto()
    COLLECTING = auto()
    RETURNING = auto()
    AT_BASE = auto()


def _own_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


class DroneAgent:
    def __init__(self):
        self._state = State.IDLE
        self._lat = DRONE_LAT
        self._lng = DRONE_LNG
        self._heading = 0.0
        self._entities: dict[int, dict] = {}

        self._central = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"drone-central-{DRONE_ID}")
        self._central.on_connect = self._on_central_connect
        self._central.on_message = self._on_central_message

        self._vanetza = VanetzaClient(client_id=f"drone-vanetza-{DRONE_ID}")
        self._vanetza.on_cam(self._on_cam)
        self._vanetza.on_denm(self._on_denm)

    def _on_central_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe("sim/announce/+")
        print(f"Drone {DRONE_ID} connected to mqtt-central: {reason_code}", flush=True)

    def _on_central_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            return
        self._entities[payload["station_id"]] = payload

    def _on_cam(self, payload: dict):
        try:
            sid = payload["stationID"]
            st = payload["fields"]["cam"]["camParameters"]["basicContainer"].get("stationType")
            print(f"Drone {DRONE_ID} received CAM from stationId={sid} stationType={st}", flush=True)
        except KeyError:
            pass

    def _on_denm(self, payload: dict):
        print(f"Drone {DRONE_ID} received DENM: {json.dumps(payload)}", flush=True)

    def _announce(self, ip: str):
        self._central.publish(f"sim/announce/{DRONE_ID}", json.dumps({
            "station_id":     DRONE_ID,
            "mac":            DRONE_MAC,
            "container_name": CONTAINER_NAME,
            "ip":             ip,
            "lat":            self._lat,
            "lng":            self._lng,
            "entity_type":    "drone",
        }), retain=True)

    def run(self):
        self._central.connect(MQTT_CENTRAL_HOST, MQTT_CENTRAL_PORT)
        self._central.loop_start()

        self._vanetza.connect()

        ip = _own_ip()
        self._announce(ip)
        print(f"Drone {DRONE_ID} announced at {ip} ({self._lat}, {self._lng})", flush=True)

        self._state = State.EXPLORING
        print(f"Drone {DRONE_ID} state → EXPLORING", flush=True)

        while True:
            start = time.monotonic()
            self._tick()
            elapsed = time.monotonic() - start
            time.sleep(max(0, TICK_MS / 1000 - elapsed))

    def _tick(self):
        self._vanetza.publish_cam(self._lat, self._lng, self._heading, DRONE_SPEED)


if __name__ == "__main__":
    DroneAgent().run()
