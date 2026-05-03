import itertools
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
    def __init__(self):
        self._drone_range: float = float(os.getenv("DRONE_RANGE_M", "150"))
        self._base_range: float = float(os.getenv("BASE_RANGE_M", "300"))
        self._tick_ms: int = int(os.getenv("TICK_REAL_MS", "500"))
        _num_drones = int(os.getenv("NUM_DRONES", "0"))
        _num_sensors = int(os.getenv("NUM_SENSORS", "2"))
        self._expected: int = _num_drones + _num_sensors + 1  # +1 for base station
        self._meta = {
            "sim_area": {
                "sw_lat": float(os.getenv("SIM_AREA_SW_LAT", "40.630")),
                "sw_lng": float(os.getenv("SIM_AREA_SW_LNG", "-8.660")),
                "width_m": float(os.getenv("SIM_AREA_WIDTH_M", "1000")),
                "height_m": float(os.getenv("SIM_AREA_HEIGHT_M", "1000")),
            },
            "num_drones": _num_drones,
            "num_sensors": _num_sensors,
        }
        self._entities: dict[int, Entity] = {}
        self._matrix = ConnectivityMatrix()
        self._tick = 0
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="proximity-manager")
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Connected to mqtt-central: {reason_code}", flush=True)
        client.subscribe("sim/announce/+")
        client.subscribe("+/vanetza/own/cam")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            return
        if msg.topic.startswith("sim/announce/"):
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
            payload["entity_type"],
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
        connected = []
        for a, b in itertools.combinations(self._entities.values(), 2):
            dist = haversine(a.lat, a.lng, b.lat, b.lng)
            in_range = dist <= self._range_between(a, b)
            self._matrix.update(a, b, in_range)
            if in_range and not (a.entity_type == "sensor" and b.entity_type == "sensor"):
                connected.append([a.station_id, b.station_id])
        self._client.publish("sim/links", json.dumps({"connected": connected, "tick": self._tick}))
        self._tick += 1

    def _block_all(self):
        for a, b in itertools.combinations(self._entities.values(), 2):
            if a.has_vanetza and b.has_vanetza:
                block(a.container_name, b.mac)
                block(b.container_name, a.mac)
            self._matrix.seed_blocked(a.container_name, b.container_name)
        print(f"Blocked all vanetza pairs", flush=True)

    def _wait_for_entities(self):
        print(f"Waiting for {self._expected} entities...", flush=True)
        while len(self._entities) < self._expected:
            time.sleep(0.5)
        print(f"All {self._expected} entities announced", flush=True)

    def _confirm_filters(self):
        deadline = time.monotonic() + 30
        vanetza = [e for e in self._entities.values() if e.has_vanetza]
        if len(vanetza) < 2:
            return
        while time.monotonic() < deadline:
            self._block_all()
            a, b = vanetza[0], vanetza[1]
            if filter_present(a.container_name, b.mac):
                break
            print("Filter not confirmed — retrying in 1s...", flush=True)
            time.sleep(1)

    def run(self):
        self._client.connect(MQTT_HOST, MQTT_PORT)
        self._client.loop_start()
        # Publish sim/meta immediately (static config known at startup)
        self._client.publish("sim/meta", json.dumps(self._meta), retain=True)
        print("Published sim/meta", flush=True)
        self._wait_for_entities()
        self._confirm_filters()
        while True:
            start = time.monotonic()
            self._do_tick()
            time.sleep(max(0, self._tick_ms / 1000 - (time.monotonic() - start)))
