from __future__ import annotations

import json

import paho.mqtt.client as mqtt

from coverage_grid import CellState, CoverageGrid, Position


class GridSync:
    """DTN-style full-grid exchange triggered when a new peer drone is first seen."""

    def __init__(self, station_id: int, grid: CoverageGrid, central_client: mqtt.Client):
        self._station_id = station_id
        self._grid = grid
        self._client = central_client
        self._synced_peers: set[int] = set()

    @property
    def topic(self) -> str:
        return f"sim/grid_sync/{self._station_id}"

    def on_peer_seen(self, peer_id: int) -> None:
        """Send our full grid snapshot to a peer the first time we see their CAM."""
        if peer_id in self._synced_peers:
            return
        self._synced_peers.add(peer_id)
        print(f"[GridSync {self._station_id}] initial sync → {peer_id}", flush=True)
        self._publish_to(peer_id)

    def broadcast_update(self) -> None:
        """Push the current grid to all previously seen peers.

        Call after significant local grid changes (e.g. SENSOR_FOUND) so that
        drones now out of DENM range still receive the update via mqtt-central.
        """
        for peer_id in self._synced_peers:
            self._publish_to(peer_id)
        if self._synced_peers:
            print(f"[GridSync {self._station_id}] broadcast update → {len(self._synced_peers)} peer(s)", flush=True)

    def on_message(self, payload: dict) -> None:
        """Merge an incoming grid snapshot into our own grid."""
        updates = self._merge(payload)
        print(f"[GridSync {self._station_id}] received snapshot → {updates} cell(s) updated", flush=True)

    def _publish_to(self, peer_id: int) -> None:
        self._client.publish(
            f"sim/grid_sync/{peer_id}",
            json.dumps({"cells": self._grid.all_cells()}),
        )

    def _merge(self, payload: dict) -> int:
        updates = 0
        for r, row in enumerate(payload.get("cells", [])):
            for c, raw in enumerate(row):
                try:
                    incoming = CellState(raw)
                except ValueError:
                    continue
                pos = Position(r, c)
                if incoming > self._grid.get(pos):
                    self._grid.set(pos, incoming)
                    updates += 1
        return updates
