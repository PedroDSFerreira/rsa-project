from __future__ import annotations

import json
import time
from enum import Enum, auto

import paho.mqtt.client as mqtt

from algorithms import make_algorithm
from comms.cell_radio import CellRadio
from comms.grid_sync import GridSync
from comms.vanetza_client import VanetzaClient
from coverage_grid import CellState, CoverageGrid, Position
from drone.collector import Collector
from drone.config import DroneConfig
from drone.motion import own_ip
from drone.navigator import ExploringStep, Navigator


class State(Enum):
    IDLE = auto()
    EXPLORING = auto()
    COLLECTING = auto()
    RETURNING = auto()
    AT_BASE = auto()


class DroneAgent:
    def __init__(self, config: DroneConfig):
        self._config = config
        self._state = State.IDLE
        self._entities: dict[int, dict] = {}
        self._collected_sensors: set[int] = set()
        self._base_location: tuple[float, float] | None = None
        self._pending_start: dict | None = None
        self._at_base_delivered = False
        self._known_peers: set[int] = set()
        self._grid_sync: GridSync | None = None

        self._central = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"drone-central-{config.drone_id}",
        )
        self._central.on_connect = self._on_central_connect
        self._central.on_message = self._on_central_message

        vanetza = VanetzaClient(client_id=f"drone-vanetza-{config.drone_id}")
        self._radio = CellRadio(drone_id=config.drone_id, vanetza=vanetza)
        self._radio.on_base_location(self._on_base_location)
        self._radio.on_peer_cam(self._on_peer_cam)
        self._radio.on_cell_update(self._on_cell_update)

        self._navigator = Navigator(config, self._radio)
        self._collector = Collector(config.drone_id, self._central, config.collection_time_s)
        self._vanetza = vanetza

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._central.connect(self._config.mqtt_host, self._config.mqtt_port)
        self._central.loop_start()
        self._vanetza.connect()

    def announce(self) -> None:
        ip = own_ip()
        self._central.publish(f"sim/announce/{self._config.drone_id}", json.dumps({
            "station_id":     self._config.drone_id,
            "mac":            self._config.mac,
            "container_name": self._config.container_name,
            "ip":             ip,
            "lat":            self._navigator.lat,
            "lng":            self._navigator.lng,
            "entity_type":    "drone",
        }), retain=True)
        print(f"Drone {self._config.drone_id} announced at {ip} ({self._navigator.lat}, {self._navigator.lng})", flush=True)

    def run(self) -> None:
        tick_s = self._config.tick_ms / 1000
        while True:
            start = time.monotonic()
            try:
                self._tick()
            except Exception as e:
                print(f"Drone {self._config.drone_id} tick error: {e}", flush=True)
            time.sleep(max(0, tick_s - (time.monotonic() - start)))

    # ── Tick ───────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        self._radio.publish_cam(self._navigator.lat, self._navigator.lng, self._navigator.heading, self._config.speed_m_s)
        self._navigator.expire_claims()

        if self._state == State.IDLE:
            return
        elif self._state == State.EXPLORING:
            self._tick_exploring()
        elif self._state == State.RETURNING:
            self._tick_returning()
        elif self._state == State.AT_BASE and not self._at_base_delivered:
            self._at_base_delivered = True
            self._collector.deliver(self._entities.get(1))

    def _tick_exploring(self) -> None:
        step = self._navigator.tick_exploring()
        if step.done:
            print(f"Drone {self._config.drone_id} all cells covered → RETURNING", flush=True)
            self._state = State.RETURNING
        elif step.sensor_id is not None:
            self._collected_sensors.add(step.sensor_id)
            self._state = State.COLLECTING
            try:
                self._collector.collect(step.sensor_id, self._entities.get(step.sensor_id), self._navigator.grid, self._radio)
            finally:
                self._state = State.EXPLORING

    def _tick_returning(self) -> None:
        base_lat, base_lng = self._base_location
        if self._navigator.tick_returning(base_lat, base_lng):
            print(f"Drone {self._config.drone_id} arrived at base → AT_BASE", flush=True)
            self._state = State.AT_BASE

    # ── MQTT central handlers ──────────────────────────────────────────────

    def _on_central_connect(self, client, userdata, flags, reason_code, properties) -> None:
        client.subscribe("sim/announce/+")
        client.subscribe("sim/start")
        client.subscribe("sim/links")
        client.subscribe(f"sensor/+/response/{self._config.drone_id}")
        print(f"Drone {self._config.drone_id} connected to mqtt-central: {reason_code}", flush=True)

    def _on_central_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            return
        topic = msg.topic
        if topic.startswith("sim/announce/"):
            self._entities[payload["station_id"]] = payload
        elif topic == "sim/start":
            self._on_sim_start(payload)
        elif topic == "sim/links":
            self._on_links(payload)
        elif topic.startswith("sensor/") and topic.endswith(f"/response/{self._config.drone_id}"):
            self._on_sensor_response(topic, payload)
        elif self._grid_sync and topic == self._grid_sync.topic:
            self._grid_sync.on_message(payload)

    def _on_sim_start(self, payload: dict) -> None:
        if self._state != State.IDLE:
            return
        if self._base_location is not None:
            self._start_mission(payload)
        else:
            self._pending_start = payload

    def _on_links(self, payload: dict) -> None:
        in_range: set[int] = set()
        for id_a, id_b in payload.get("connected", []):
            if id_a == self._config.drone_id:
                in_range.add(id_b)
            elif id_b == self._config.drone_id:
                in_range.add(id_a)
        self._radio.set_in_range_peers(in_range)

        if self._state not in (State.EXPLORING, State.COLLECTING):
            return
        for id_a, id_b in payload.get("connected", []):
            sensor_id = None
            if id_a == self._config.drone_id and self._is_sensor(id_b):
                sensor_id = id_b
            elif id_b == self._config.drone_id and self._is_sensor(id_a):
                sensor_id = id_a
            if sensor_id and sensor_id not in self._collected_sensors:
                sensor = self._entities.get(sensor_id)
                if sensor and not self._navigator.is_sensor_found(sensor["lat"], sensor["lng"]):
                    if self._navigator.should_collect_sensor(sensor_id):
                        self._navigator.redirect_to_sensor(sensor_id, sensor["lat"], sensor["lng"])
                break

    def _on_sensor_response(self, topic: str, payload: dict) -> None:
        try:
            self._collector.handle_response(int(topic.split("/")[1]), payload)
        except (ValueError, IndexError):
            pass

    # ── Radio event handlers ───────────────────────────────────────────────

    def _on_base_location(self, lat: float, lng: float) -> None:
        self._base_location = (lat, lng)
        if self._state == State.IDLE and self._pending_start:
            self._start_mission(self._pending_start)
            self._pending_start = None

    def _on_peer_cam(self, peer_id: int) -> None:
        if self._grid_sync and peer_id not in self._known_peers:
            self._known_peers.add(peer_id)
            self._grid_sync.on_peer_seen(peer_id)

    def _on_cell_update(self, cell_index: int, state: CellState, validity: int) -> None:
        self._navigator.on_cell_update(cell_index, state, validity)

    # ── Mission start ──────────────────────────────────────────────────────

    def _start_mission(self, payload: dict) -> None:
        m = payload["map"]
        grid = CoverageGrid(
            sw_lat=m["sw_lat"], sw_lng=m["sw_lng"],
            width_m=m["width_m"], height_m=m["height_m"],
            cell_size_m=m["cell_size_m"],
        )
        drone_starts = payload["drone_starts"]
        my_start = next(s for s in drone_starts if s["drone_id"] == self._config.drone_id)
        start = Position(my_start["row"], my_start["col"])
        all_starts = sorted([Position(s["row"], s["col"]) for s in drone_starts], key=lambda p: p.row)

        algorithm = make_algorithm(payload["algorithm"])
        self._navigator.start(grid, start, all_starts, algorithm)

        self._grid_sync = GridSync(self._config.drone_id, grid, self._central)
        self._central.subscribe(self._grid_sync.topic)
        self._state = State.EXPLORING
        print(
            f"Drone {self._config.drone_id} → EXPLORING "
            f"(start row {my_start['row']}, algorithm={payload['algorithm']}, base at {self._base_location})",
            flush=True,
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _is_sensor(self, station_id: int) -> bool:
        entity = self._entities.get(station_id)
        return entity is not None and entity.get("entity_type") == "sensor"
