from __future__ import annotations

import json
import math
import os
import socket
import threading
import time
from enum import Enum, auto

import paho.mqtt.client as mqtt

from coverage_grid import CellState, CoverageGrid
from grid_sync import GridSync
from traversal import GreedyNearestTraversal, Strip, make_traversal
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
COLLECTION_TIME_S = float(os.getenv("DRONE_COLLECTION_TIME_S", "3.0"))

METERS_PER_LAT = 111000.0


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


def _meters_per_lng(lat: float) -> float:
    return METERS_PER_LAT * math.cos(math.radians(lat))


def _distance_m(lat: float, lng: float, tlat: float, tlng: float) -> float:
    dlat = (tlat - lat) * METERS_PER_LAT
    dlng = (tlng - lng) * _meters_per_lng(lat)
    return math.hypot(dlat, dlng)


def _heading_deg(lat: float, lng: float, tlat: float, tlng: float) -> float:
    dlat = (tlat - lat) * METERS_PER_LAT
    dlng = (tlng - lng) * _meters_per_lng(lat)
    return math.degrees(math.atan2(dlng, dlat)) % 360


def _step_toward(lat: float, lng: float, tlat: float, tlng: float, step_m: float) -> tuple[float, float]:
    dlat = (tlat - lat) * METERS_PER_LAT
    dlng = (tlng - lng) * _meters_per_lng(lat)
    length = math.hypot(dlat, dlng)
    lat += (dlat / length) * step_m / METERS_PER_LAT
    lng += (dlng / length) * step_m / _meters_per_lng(lat)
    return lat, lng


class DroneAgent:
    def __init__(self):
        self._state = State.IDLE
        self._lat = DRONE_LAT
        self._lng = DRONE_LNG
        self._heading = 0.0

        # Discovered at runtime — not assumed from env
        self._base_location: tuple[float, float] | None = None
        self._pending_start: dict | None = None  # sim/start buffered until base location is known

        self._grid: CoverageGrid | None = None
        self._strip: Strip | None = None
        self._traversal = None
        self._cell_size_m = 50.0
        self._waypoint: tuple[int, int] | None = None
        self._waypoint_pos: tuple[float, float] | None = None
        self._grid_sync: GridSync | None = None
        self._known_peers: set[int] = set()
        self._claim_expiry: dict[int, float] = {}

        self._entities: dict[int, dict] = {}
        self._in_range_peers: set[int] = set()  # updated from sim/links; used when MAC filtering is unavailable
        self._collected_data: list[dict] = []
        self._collected_sensors: set[int] = set()
        self._sensor_target_id: int | None = None       # sensor to navigate to before collecting
        self._current_collection_sensor_id: int | None = None  # guards response handler
        self._at_base_delivered = False
        self._sensor_response: dict | None = None
        self._sensor_response_event = threading.Event()

        self._central = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"drone-central-{DRONE_ID}")
        self._central.on_connect = self._on_central_connect
        self._central.on_message = self._on_central_message

        self._vanetza = VanetzaClient(client_id=f"drone-vanetza-{DRONE_ID}")
        self._vanetza.on_cam(self._on_cam)
        self._vanetza.on_denm(self._on_denm)

    # ── MQTT handlers ──────────────────────────────────────────────────────

    def _on_central_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe("sim/announce/+")
        client.subscribe("sim/start")
        client.subscribe("sim/links")
        client.subscribe(f"sensor/+/response/{DRONE_ID}")
        print(f"Drone {DRONE_ID} connected to mqtt-central: {reason_code}", flush=True)

    def _on_central_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            return
        if msg.topic.startswith("sim/announce/"):
            self._entities[payload["station_id"]] = payload
        elif msg.topic == "sim/start":
            self._on_sim_start(payload)
        elif msg.topic == "sim/links":
            self._on_links(payload)
        elif msg.topic.startswith("sensor/") and msg.topic.endswith(f"/response/{DRONE_ID}"):
            try:
                responding_sid = int(msg.topic.split("/")[1])
                if responding_sid == self._current_collection_sensor_id:
                    self._sensor_response = payload
                    self._sensor_response_event.set()
            except (ValueError, IndexError):
                pass
        elif self._grid_sync and msg.topic == self._grid_sync.topic:
            self._grid_sync.on_message(payload)

    def _on_sim_start(self, payload: dict):
        if self._state != State.IDLE:
            return
        if self._base_location is not None:
            self._start_exploring(payload)
        else:
            self._pending_start = payload

    def _on_links(self, payload: dict):
        # Always keep the in-range peer set current (used as fallback when
        # MAC-level ebtables filtering is unavailable, e.g. on WSL2).
        in_range: set[int] = set()
        for id_a, id_b in payload.get("connected", []):
            if id_a == DRONE_ID:
                in_range.add(id_b)
            elif id_b == DRONE_ID:
                in_range.add(id_a)
        self._in_range_peers = in_range

        if self._state not in (State.EXPLORING, State.COLLECTING):
            return
        if self._sensor_target_id is not None:
            return
        for id_a, id_b in payload.get("connected", []):
            sensor_id = None
            if id_a == DRONE_ID and self._is_sensor(id_b):
                sensor_id = id_b
            elif id_b == DRONE_ID and self._is_sensor(id_a):
                sensor_id = id_a
            if sensor_id and sensor_id not in self._collected_sensors:
                self._sensor_target_id = sensor_id
                break

    def _on_cam(self, payload: dict):
        try:
            params = payload["fields"]["cam"]["camParameters"]
            st = params["basicContainer"].get("stationType")
            if st == 15:
                # Base station: always accept — needed for initial location discovery
                pos = params["basicContainer"]["referencePosition"]
                self._base_location = (pos["latitude"], pos["longitude"])
                if self._state == State.IDLE and self._pending_start:
                    self._start_exploring(self._pending_start)
                    self._pending_start = None
            elif st == 10:
                sid = payload["stationID"]
                # Application-level proximity filter: ignore peers not listed in sim/links.
                # This is the fallback when MAC-level ebtables filtering is unavailable (e.g. WSL2).
                if sid not in self._in_range_peers:
                    return
                if sid != DRONE_ID and self._grid_sync:
                    if sid not in self._known_peers:
                        self._known_peers.add(sid)
                        self._grid_sync.on_peer_seen(sid)
        except KeyError:
            pass

    def _on_denm(self, payload: dict):
        if self._grid is None:
            return
        try:
            denm = payload.get("fields", {}).get("denm") or payload
            mgmt = denm["management"]
            originator = mgmt["actionId"]["originatingStationId"]
            if originator == DRONE_ID:
                return
            # Application-level proximity filter (fallback when ebtables is unavailable)
            if self._in_range_peers and originator not in self._in_range_peers:
                return
            encoded = mgmt["actionId"]["sequenceNumber"]
            cell_index, sub_cause = divmod(encoded, 4)
            validity = mgmt.get("validityDuration", 60)
            row, col = self._grid.cell_from_index(cell_index)
            state_map = {0: CellState.CLAIMED, 1: CellState.VISITED, 2: CellState.SENSOR_FOUND}
            new_state = state_map.get(sub_cause)
            if new_state is None:
                return
            if new_state > self._grid.get(row, col):
                self._grid.set(row, col, new_state)
            if new_state == CellState.CLAIMED:
                self._claim_expiry[cell_index] = time.monotonic() + validity
            elif cell_index in self._claim_expiry:
                del self._claim_expiry[cell_index]
        except (KeyError, IndexError, ValueError):
            pass

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def _start_exploring(self, payload: dict):
        m = payload["map"]
        self._grid = CoverageGrid(
            sw_lat=m["sw_lat"], sw_lng=m["sw_lng"],
            width_m=m["width_m"], height_m=m["height_m"],
            cell_size_m=m["cell_size_m"],
        )
        self._cell_size_m = m["cell_size_m"]

        drone_index = DRONE_ID - 10
        strip_data = next(s for s in payload["strips"] if s["drone_index"] == drone_index)
        self._strip = Strip(row_min=strip_data["row_min"], row_max=strip_data["row_max"])
        self._traversal = make_traversal(payload["algorithm"], self._strip, self._grid.cols)
        self._grid_sync = GridSync(DRONE_ID, self._grid, self._central)
        self._central.subscribe(self._grid_sync.topic)

        self._state = State.EXPLORING
        print(
            f"Drone {DRONE_ID} → EXPLORING "
            f"(strip rows {self._strip.row_min}–{self._strip.row_max}, "
            f"base at {self._base_location})",
            flush=True,
        )

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

        while True:
            start = time.monotonic()
            try:
                self._tick()
            except Exception as e:
                print(f"Drone {DRONE_ID} tick error: {e}", flush=True)
            elapsed = time.monotonic() - start
            time.sleep(max(0, TICK_MS / 1000 - elapsed))

    # ── Tick ───────────────────────────────────────────────────────────────

    def _tick(self):
        self._vanetza.publish_cam(self._lat, self._lng, self._heading, DRONE_SPEED)
        self._expire_stale_claims()

        if self._state == State.IDLE:
            return
        elif self._state == State.EXPLORING:
            self._tick_exploring()
        elif self._state == State.RETURNING:
            self._tick_returning()
        elif self._state == State.AT_BASE:
            if not self._at_base_delivered:
                self._at_base_delivered = True
                self._deliver_data()

    def _expire_stale_claims(self):
        if self._grid is None or not self._claim_expiry:
            return
        now = time.monotonic()
        expired = [idx for idx, exp in self._claim_expiry.items() if now >= exp]
        for cell_index in expired:
            del self._claim_expiry[cell_index]
            row, col = self._grid.cell_from_index(cell_index)
            if self._grid.get(row, col) == CellState.CLAIMED:
                self._grid.set(row, col, CellState.UNKNOWN)

    def _tick_exploring(self):
        if self._sensor_target_id is not None:
            self._tick_goto_sensor()
            return

        if self._waypoint is None:
            nxt = self._traversal.next_waypoint(self._grid, (self._lat, self._lng))
            if nxt is None:
                self._traversal = GreedyNearestTraversal()
                nxt = self._traversal.next_waypoint(self._grid, (self._lat, self._lng))
            if nxt is None:
                print(f"Drone {DRONE_ID} all cells covered → RETURNING", flush=True)
                self._state = State.RETURNING
                return
            self._waypoint = nxt
            self._waypoint_pos = self._grid.cell_to_coords(*nxt)
            self._grid.set(*nxt, CellState.CLAIMED)
            cell_idx = self._grid.cell_index(*nxt)
            cell_lat, cell_lng = self._waypoint_pos
            validity = max(10, int(self._cell_size_m / DRONE_SPEED * 4))
            self._publish_cell_state(cell_idx, 0, cell_lat, cell_lng, validity)

        target_lat, target_lng = self._waypoint_pos
        step = DRONE_SPEED * (TICK_MS / 1000)
        dist = _distance_m(self._lat, self._lng, target_lat, target_lng)

        if dist <= step:
            self._lat, self._lng = target_lat, target_lng
            row, col = self._waypoint
            self._grid.set(row, col, CellState.VISITED)
            cell_idx = self._grid.cell_index(row, col)
            self._publish_cell_state(cell_idx, 1, target_lat, target_lng)
            print(f"Drone {DRONE_ID} visited ({row},{col})", flush=True)
            self._waypoint = None
            self._waypoint_pos = None
        else:
            self._heading = _heading_deg(self._lat, self._lng, target_lat, target_lng)
            self._lat, self._lng = _step_toward(self._lat, self._lng, target_lat, target_lng, step)

    def _tick_goto_sensor(self):
        """Navigate to the target sensor's position, then collect once arrived."""
        sensor = self._entities.get(self._sensor_target_id)
        if sensor is None:
            return  # Entity info not yet received; wait

        slat, slng = sensor["lat"], sensor["lng"]
        step = DRONE_SPEED * (TICK_MS / 1000)
        dist = _distance_m(self._lat, self._lng, slat, slng)

        if dist <= step:
            self._lat, self._lng = slat, slng
            sensor_id = self._sensor_target_id
            self._sensor_target_id = None
            self._abandon_waypoint()
            self._state = State.COLLECTING
            try:
                self._collect_sensor(sensor_id)
            finally:
                self._state = State.EXPLORING
        else:
            self._heading = _heading_deg(self._lat, self._lng, slat, slng)
            self._lat, self._lng = _step_toward(self._lat, self._lng, slat, slng, step)

    def _abandon_waypoint(self):
        """Revert a claimed-but-unvisited waypoint back to UNKNOWN so it can be re-claimed."""
        if self._waypoint is not None and self._grid is not None:
            row, col = self._waypoint
            if self._grid.get(row, col) == CellState.CLAIMED:
                self._grid.set(row, col, CellState.UNKNOWN)
        self._waypoint = None
        self._waypoint_pos = None

    def _tick_returning(self):
        base_lat, base_lng = self._base_location
        step = DRONE_SPEED * (TICK_MS / 1000)
        dist = _distance_m(self._lat, self._lng, base_lat, base_lng)
        if dist <= step:
            self._lat, self._lng = base_lat, base_lng
            print(f"Drone {DRONE_ID} arrived at base → AT_BASE", flush=True)
            self._state = State.AT_BASE
            return
        self._heading = _heading_deg(self._lat, self._lng, base_lat, base_lng)
        self._lat, self._lng = _step_toward(self._lat, self._lng, base_lat, base_lng, step)

    # ── Sensor collection & data delivery ──────────────────────────────────

    def _publish_cell_state(self, cell_idx: int, sub_cause: int, lat: float, lng: float, validity: int = 60):
        """Publish cell state as a DENM. Vanetza echoes it to vanetza/time/denm (VANETZA_DENM_MQTT_TIME_ENABLED=true),
        which the remote broker bridge forwards to mqtt-central for dashboard consumption."""
        self._vanetza.publish_denm(
            lat, lng,
            sub_cause_code=sub_cause,
            cell_index=cell_idx,
            station_id=DRONE_ID,
            validity_duration=validity,
        )

    def _collect_sensor(self, sensor_id: int):
        self._collected_sensors.add(sensor_id)
        sensor = self._entities.get(sensor_id)
        if not sensor:
            return
        print(f"Drone {DRONE_ID} collecting from sensor {sensor_id} (transfer time: {COLLECTION_TIME_S}s)", flush=True)

        self._current_collection_sensor_id = sensor_id
        self._sensor_response = None
        self._sensor_response_event.clear()
        self._central.publish(
            f"sensor/{sensor_id}/request",
            json.dumps({"requester_id": DRONE_ID}),
        )

        # Wait for sensor acknowledgement (fast network round-trip)
        self._sensor_response_event.wait(timeout=5.0)
        self._current_collection_sensor_id = None

        data = self._sensor_response
        if not data:
            print(f"Drone {DRONE_ID} sensor {sensor_id} collection timed out", flush=True)
            return

        # Simulate data transfer duration — drone stays put in COLLECTING state
        time.sleep(COLLECTION_TIME_S)

        self._collected_data.append({"sensor_id": sensor_id, "payload": data})

        slat, slng = sensor["lat"], sensor["lng"]
        row, col = self._grid.coords_to_cell(slat, slng)
        self._grid.set(row, col, CellState.SENSOR_FOUND)
        cell_idx = self._grid.cell_index(row, col)
        self._publish_cell_state(cell_idx, 2, slat, slng)
        print(f"Drone {DRONE_ID} collected sensor {sensor_id} → {len(self._collected_data)} total", flush=True)

    def _deliver_data(self):
        base = self._entities.get(1)
        if not base:
            print(f"Drone {DRONE_ID} base station not in entity registry", flush=True)
            return

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"drone-deliver-{DRONE_ID}",
        )
        client.connect(base["ip"], 1883)
        client.loop_start()
        client.publish("sim/base/data_delivery", json.dumps({
            "drone_id": DRONE_ID,
            "data":     self._collected_data,
        }))
        time.sleep(0.5)
        client.loop_stop()
        client.disconnect()
        print(
            f"Drone {DRONE_ID} delivered {len(self._collected_data)} sensor datasets to base",
            flush=True,
        )

    def _is_sensor(self, station_id: int) -> bool:
        entity = self._entities.get(station_id)
        return entity is not None and entity.get("entity_type") == "sensor"


if __name__ == "__main__":
    DroneAgent().run()
