from __future__ import annotations

import json
import threading
import time

import paho.mqtt.client as mqtt

from comms.cell_radio import CellRadio
from coverage_grid import CellState, CoverageGrid, Position


class Collector:
    """Handles sensor data collection and delivery to the base station."""

    def __init__(self, drone_id: int, central: mqtt.Client, collection_time_s: float):
        self._drone_id = drone_id
        self._central = central
        self._collection_time_s = collection_time_s
        self._current_sensor_id: int | None = None
        self._response: dict | None = None
        self._response_event = threading.Event()
        self._collected: list[dict] = []

    def handle_response(self, sensor_id: int, payload: dict) -> None:
        """Deliver an incoming sensor response to the waiting collect() call."""
        if sensor_id == self._current_sensor_id:
            self._response = payload
            self._response_event.set()

    def collect(self, sensor_id: int, sensor: dict | None, grid: CoverageGrid, radio: CellRadio) -> None:
        if sensor is None:
            return
        print(f"Drone {self._drone_id} collecting from sensor {sensor_id} (transfer: {self._collection_time_s}s)", flush=True)

        self._current_sensor_id = sensor_id
        self._response = None
        self._response_event.clear()
        self._central.publish(f"sensor/{sensor_id}/request", json.dumps({"requester_id": self._drone_id}))

        self._response_event.wait(timeout=5.0)
        self._current_sensor_id = None

        if not self._response:
            print(f"Drone {self._drone_id} sensor {sensor_id} collection timed out", flush=True)
            return

        time.sleep(self._collection_time_s)

        self._collected.append({"sensor_id": sensor_id, "payload": self._response})

        slat, slng = sensor["lat"], sensor["lng"]
        pos = grid.coords_to_cell(slat, slng)
        grid.set(pos, CellState.SENSOR_FOUND)
        radio.publish_cell_state(grid.cell_index(pos), CellState.SENSOR_FOUND, slat, slng)
        print(f"Drone {self._drone_id} collected sensor {sensor_id} → {len(self._collected)} total", flush=True)

    def deliver(self, base: dict | None) -> None:
        if base is None:
            print(f"Drone {self._drone_id} base station not in entity registry", flush=True)
            return
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"drone-deliver-{self._drone_id}")
        client.connect(base["ip"], 1883)
        client.loop_start()
        client.publish("sim/base/data_delivery", json.dumps({"drone_id": self._drone_id, "data": self._collected}))
        time.sleep(0.5)
        client.loop_stop()
        client.disconnect()
        print(f"Drone {self._drone_id} delivered {len(self._collected)} sensor datasets to base", flush=True)
