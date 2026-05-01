import json
import os
import time

import paho.mqtt.client as mqtt

from connectivity import ConnectivityMatrix
from entity import Entity
from geo import haversine
from mac_filter import block, filter_present

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt-central")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


class ProximityManager:
    def __init__(self, config: dict):
        self._drone_range: float = config["radio"]["drone_range_m"]
        self._base_range: float = config["radio"]["base_range_m"]
        self._tick_ms: int = config["simulation"]["tick_real_ms"]
        self._expected: int = config["entities"]["num_drones"] + config["entities"]["num_sensors"]
        self._meta = {
            "map": config["map"],
            "num_drones": config["entities"]["num_drones"],
            "num_sensors": config["entities"]["num_sensors"],
        }
        self._entities: dict[int, Entity] = {}
        self._matrix = ConnectivityMatrix()
        self._tick = 0
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="proximity-manager")
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

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
        if station_id in self._entities:
            return
        self._entities[station_id] = Entity(
            station_id,
            payload["container_name"],
            payload["mac"],
            payload["lat"],
            payload["lng"],
        )
        print(
            f"Announced: stationId={station_id} container={payload['container_name']}"
            f" type={payload['entity_type']} ({len(self._entities)}/{self._expected})",
            flush=True,
        )

    def _handle_cam(self, payload: dict):
        try:
            sid = payload["stationID"]
            pos = payload["fields"]["cam"]["camParameters"]["basicContainer"]["referencePosition"]
            if sid in self._entities:
                self._entities[sid].lat = pos["latitude"]
                self._entities[sid].lng = pos["longitude"]
        except KeyError:
            pass

    def _range_between(self, a: Entity, b: Entity) -> float:
        return self._base_range if a.station_id == 1 or b.station_id == 1 else self._drone_range

    def _do_tick(self):
        ids = list(self._entities.keys())
        connected = []
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a = self._entities[ids[i]]
                b = self._entities[ids[j]]
                dist = haversine(a.lat, a.lng, b.lat, b.lng)
                self._matrix.update(a.container_name, b.container_name, a.mac, b.mac, dist <= self._range_between(a, b))
                if dist <= self._range_between(a, b):
                    connected.append([a.station_id, b.station_id])
        self._client.publish("sim/links", json.dumps({"connected": connected, "tick": self._tick}))
        self._tick += 1

    def _block_all(self):
        ids = list(self._entities.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a = self._entities[ids[i]]
                b = self._entities[ids[j]]
                block(a.container_name, b.mac)
                block(b.container_name, a.mac)
                self._matrix.seed_blocked(a.container_name, b.container_name)
        print(f"Blocked {len(ids)*(len(ids)-1)//2} pairs", flush=True)

    def _wait_for_entities(self):
        print(f"Waiting for {self._expected} entities...", flush=True)
        while len(self._entities) < self._expected:
            time.sleep(0.5)
        print(f"All {self._expected} entities announced", flush=True)

    def _confirm_filters(self):
        deadline = time.monotonic() + 30
        ids = list(self._entities.keys())
        while time.monotonic() < deadline:
            self._block_all()
            if len(ids) < 2:
                break
            a, b = self._entities[ids[0]], self._entities[ids[1]]
            if filter_present(a.container_name, b.mac):
                break
            print("Filter not confirmed — retrying in 1s...", flush=True)
            time.sleep(1)

    def run(self):
        self._client.connect(MQTT_HOST, MQTT_PORT)
        self._client.loop_start()
        self._wait_for_entities()
        self._confirm_filters()
        self._client.publish("sim/meta", json.dumps(self._meta), retain=True)
        print("Published sim/meta", flush=True)
        while True:
            start = time.monotonic()
            self._do_tick()
            time.sleep(max(0, self._tick_ms / 1000 - (time.monotonic() - start)))
