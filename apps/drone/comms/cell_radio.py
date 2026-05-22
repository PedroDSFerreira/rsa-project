from __future__ import annotations

from typing import Callable

from comms.vanetza_client import VanetzaClient
from coverage_grid import CellState

BaseCamCallback = Callable[[float, float], None]   # (lat, lng)
CellUpdateCallback = Callable[[int, CellState, int], None]  # cell_index, state, validity


class CellRadio:
    """Abstracts CAM and DENM protocol interactions with the Vanetza radio layer.

    Handles proximity filtering and encoding/decoding so the rest of the
    application works in terms of domain events rather than V2X messages.
    """

    def __init__(self, drone_id: int, vanetza: VanetzaClient):
        self._drone_id = drone_id
        self._vanetza = vanetza
        self._in_range_peers: set[int] = set()
        self._base_cam_callbacks: list[BaseCamCallback] = []
        self._cell_update_callbacks: list[CellUpdateCallback] = []
        vanetza.on_cam(self._handle_cam)
        vanetza.on_denm(self._handle_denm)

    def set_in_range_peers(self, peers: set[int]) -> None:
        self._in_range_peers = peers

    def on_base_location(self, callback: BaseCamCallback) -> None:
        self._base_cam_callbacks.append(callback)

    def on_cell_update(self, callback: CellUpdateCallback) -> None:
        self._cell_update_callbacks.append(callback)

    def publish_cam(self, lat: float, lng: float, heading: float, speed: float) -> None:
        self._vanetza.publish_cam(lat, lng, heading, speed)

    def publish_cell_state(
        self,
        cell_idx: int,
        state: CellState,
        lat: float,
        lng: float,
        validity: int = 60,
    ) -> None:
        sub_cause = {
            CellState.CLAIMED: 0,
            CellState.VISITED: 1,
            CellState.SENSOR_FOUND: 2,
        }.get(state)
        if sub_cause is None:
            return
        self._vanetza.publish_denm(
            lat, lng,
            sub_cause_code=sub_cause,
            cell_index=cell_idx,
            station_id=self._drone_id,
            validity_duration=validity,
        )

    # ── Internal handlers ──────────────────────────────────────────────────

    def _handle_cam(self, payload: dict) -> None:
        try:
            params = payload["fields"]["cam"]["camParameters"]
            if params["basicContainer"].get("stationType") == 15:
                pos = params["basicContainer"]["referencePosition"]
                for cb in self._base_cam_callbacks:
                    cb(pos["latitude"], pos["longitude"])
        except KeyError:
            pass

    def _handle_denm(self, payload: dict) -> None:
        try:
            denm = payload.get("fields", {}).get("denm") or payload
            mgmt = denm["management"]
            originator = mgmt["actionId"]["originatingStationId"]
            if originator == self._drone_id or originator not in self._in_range_peers:
                return
            encoded = mgmt["actionId"]["sequenceNumber"]
            cell_index, sub_cause = divmod(encoded, 4)
            validity = mgmt.get("validityDuration", 60)
            state = {0: CellState.CLAIMED, 1: CellState.VISITED, 2: CellState.SENSOR_FOUND}.get(sub_cause)
            if state is None:
                return
            print(f"[DENM {self._drone_id}] from {originator}: cell {cell_index} → {state.name}", flush=True)
            for cb in self._cell_update_callbacks:
                cb(cell_index, state, validity)
        except (KeyError, IndexError, ValueError):
            pass
