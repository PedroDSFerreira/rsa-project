import json
import math
import os
import time

import paho.mqtt.client as mqtt
import yaml

from proximity import ConnectivityMatrix

CONFIG_PATH = os.getenv("CONFIG_PATH", "/config/simulation_config.yaml")
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt-central")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class Entity:
    def __init__(self, station_id: int, container_name: str, mac: str, lat: float, lng: float):
        self.station_id = station_id
        self.container_name = container_name
        self.mac = mac
        self.lat = lat
        self.lng = lng


class ProximityManager:
    def __init__(self, config: dict):
        self.config = config
        self.drone_range = config["radio"]["drone_range_m"]
        self.base_range = config["radio"]["base_range_m"]
        self.tick_ms = config["simulation"]["tick_real_ms"]
        self.entities: dict[int, Entity] = {}
        self.matrix = ConnectivityMatrix()
        self.tick = 0
        self._expected = config["entities"]["num_drones"] + config["entities"]["num_sensors"]

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="proximity-manager")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Connected to mqtt-central: {reason_code}", flush=True)
        client.subscribe("sim/announce")
        client.subscribe("+/vanetza/own/cam")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            return

        if msg.topic == "sim/announce":
            self._handle_announce(payload)
        else:
            self._handle_cam(payload)

    def _handle_announce(self, payload: dict):
        station_id = payload["station_id"]
        if station_id not in self.entities:
            self.entities[station_id] = Entity(
                station_id,
                payload["container_name"],
                payload["mac"],
                payload["lat"],
                payload["lng"],
            )
            print(
                f"Announced: stationId={station_id} container={payload['container_name']}"
                f" type={payload['entity_type']} ({len(self.entities)}/{self._expected})",
                flush=True,
            )

    def _handle_cam(self, payload: dict):
        try:
            station_id = payload["stationID"]
            position = payload["fields"]["cam"]["camParameters"]["basicContainer"]["referencePosition"]
            lat = position["latitude"]
            lng = position["longitude"]
            if station_id in self.entities:
                self.entities[station_id].lat = lat
                self.entities[station_id].lng = lng
        except KeyError:
            pass

    def _publish_meta(self):
        meta = {
            "map": self.config["map"],
            "num_drones": self.config["entities"]["num_drones"],
            "num_sensors": self.config["entities"]["num_sensors"],
        }
        self.client.publish("sim/meta", json.dumps(meta), retain=True)

    def _publish_links(self, connected_ids: list[tuple[int, int]]):
        self.client.publish("sim/links", json.dumps({"connected": connected_ids, "tick": self.tick}))

    def _tick(self):
        ids = list(self.entities.keys())
        connected_ids = []

        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a = self.entities[ids[i]]
                b = self.entities[ids[j]]
                dist = haversine(a.lat, a.lng, b.lat, b.lng)
                threshold = self.base_range if a.station_id == 1 or b.station_id == 1 else self.drone_range
                self.matrix.update(a.container_name, b.container_name, a.mac, b.mac, dist <= threshold)
                if dist <= threshold:
                    connected_ids.append([a.station_id, b.station_id])

        self._publish_links(connected_ids)
        self.tick += 1

    def _block_all(self):
        """Block all entity pairs on startup — nodes start fully isolated."""
        from proximity import block
        ids = list(self.entities.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a = self.entities[ids[i]]
                b = self.entities[ids[j]]
                block(a.container_name, b.mac)
                block(b.container_name, a.mac)
                self.matrix._state[self.matrix._key(a.container_name, b.container_name)] = False
        print(f"Blocked all pairs: {len(ids)} nodes, {len(ids)*(len(ids)-1)//2} pairs", flush=True)

    def run(self):
        self.client.connect(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()

        print(f"Waiting for {self._expected} entities to announce...", flush=True)
        while len(self.entities) < self._expected:
            time.sleep(0.5)
        print(f"All {self._expected} entities announced — starting proximity loop", flush=True)

        from proximity import filter_present
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            self._block_all()
            ids = list(self.entities.keys())
            if len(ids) >= 2:
                a = self.entities[ids[0]]
                b = self.entities[ids[1]]
                if filter_present(a.container_name, b.mac):
                    break
            else:
                break
            print("Filter not confirmed — retrying in 1s...", flush=True)
            time.sleep(1)

        self._publish_meta()
        print("Published sim/meta", flush=True)

        while True:
            start = time.monotonic()
            self._tick()
            elapsed = time.monotonic() - start
            time.sleep(max(0, self.tick_ms / 1000 - elapsed))


if __name__ == "__main__":
    config = load_config(CONFIG_PATH)
    ProximityManager(config).run()
