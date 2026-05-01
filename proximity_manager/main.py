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

        # Pre-populate entities from static_nodes so blocking works before any CAM arrives
        for node in config.get("static_nodes", []):
            self.entities[node["station_id"]] = Entity(
                node["station_id"],
                node["container_name"],
                node["mac"],
                node["lat"],
                node["lng"],
            )

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="proximity-manager")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Connected to mqtt-central: {reason_code}")
        client.subscribe("+/vanetza/own/cam")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
            station_id = payload["stationID"]
            station_addr = payload["stationAddr"]
            position = payload["fields"]["cam"]["camParameters"]["basicContainer"]["referencePosition"]
            lat = position["latitude"]
            lng = position["longitude"]

            if station_id not in self.entities:
                container_name = f"project-node-{chr(ord('a') + station_id - 10)}-1"
                self.entities[station_id] = Entity(station_id, container_name, station_addr, lat, lng)
                print(f"Registered entity: stationId={station_id} container={container_name}")
            else:
                self.entities[station_id].lat = lat
                self.entities[station_id].lng = lng
        except (KeyError, json.JSONDecodeError):
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
                # Call block() directly and seed state as False so the matrix
                # only transitions to True (unblock) when distance is within range.
                block(a.container_name, b.mac)
                block(b.container_name, a.mac)
                self.matrix._state[self.matrix._key(a.container_name, b.container_name)] = False
        print(f"Blocked all pairs: {len(ids)} nodes, {len(ids)*(len(ids)-1)//2} pairs", flush=True)

    def run(self):
        self.client.connect(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()

        # Wait until vanetza finishes its own ingress qdisc setup, then block and
        # verify each filter actually stuck (retry up to 30s).
        import time as _t
        from proximity import filter_present
        deadline = _t.monotonic() + 30
        while _t.monotonic() < deadline:
            self._block_all()
            # Check that at least one filter landed; retry if not
            ids = list(self.entities.keys())
            if len(ids) >= 2:
                a = self.entities[ids[0]]
                b = self.entities[ids[1]]
                if filter_present(a.container_name, b.mac):
                    break
            else:
                break  # nothing to verify
            print("Filter not confirmed — retrying in 1s...", flush=True)
            _t.sleep(1)
        self._publish_meta()
        print("Published sim/meta")

        while True:
            start = time.monotonic()
            self._tick()
            elapsed = time.monotonic() - start
            time.sleep(max(0, self.tick_ms / 1000 - elapsed))


if __name__ == "__main__":
    config = load_config(CONFIG_PATH)
    ProximityManager(config).run()
