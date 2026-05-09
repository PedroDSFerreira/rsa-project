from __future__ import annotations

import json

import paho.mqtt.client as mqtt

from coverage_grid import CellState, CoverageGrid

MQTT_CENTRAL_HOST = "mqtt-central"
MQTT_CENTRAL_PORT = 1883


class GridSync:
    """Handles DTN-style grid synchronisation between peers over mqtt-central."""

    def __init__(self, station_id: int, grid: CoverageGrid, central_client: mqtt.Client):
        self._station_id = station_id
        self._grid = grid
        self._client = central_client
        self._synced_peers: set[int] = set()

    @property
    def topic(self) -> str:
        return f"sim/grid_sync/{self._station_id}"

    def on_peer_seen(self, peer_id: int) -> None:
        """Call when a CAM from a previously-unseen peer drone arrives."""
        if peer_id in self._synced_peers:
            return
        self._synced_peers.add(peer_id)
        self._publish_to(peer_id)

    def on_message(self, payload: dict) -> None:
        """Call when a sim/grid_sync/{own_id} message arrives."""
        self._merge(payload)

    def _publish_to(self, peer_id: int) -> None:
        cells = [
            [int(self._grid.get(r, c)) for c in range(self._grid.cols)]
            for r in range(self._grid.rows)
        ]
        self._client.publish(
            f"sim/grid_sync/{peer_id}",
            json.dumps({"cells": cells}),
        )

    def _merge(self, payload: dict) -> None:
        cells = payload.get("cells", [])
        for r, row in enumerate(cells):
            for c, raw in enumerate(row):
                try:
                    incoming = CellState(raw)
                except ValueError:
                    continue
                if incoming > self._grid.get(r, c):
                    self._grid.set(r, c, incoming)
