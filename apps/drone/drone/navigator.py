from __future__ import annotations

import time
from dataclasses import dataclass

from algorithms.base import Algorithm
from comms.cell_radio import CellRadio
from coverage_grid import CellState, CoverageGrid, Position
from drone.config import DroneConfig
from drone.motion import distance_m, heading_deg, step_toward


@dataclass
class ExploringStep:
    """Outcome of a single exploration tick."""
    done: bool = False
    sensor_id: int | None = None  # set when the drone has just arrived at a sensor waypoint


class Navigator:
    """Owns drone position and delegates coverage decisions to the Algorithm.

    Handles waypoint navigation, claim broadcasting, cell-state merging from
    received DENMs (forwarding updates to the algorithm hook), and stale-claim
    expiry. Zone boundaries live entirely inside the Algorithm implementation.
    """

    def __init__(self, config: DroneConfig, radio: CellRadio):
        self._config = config
        self._radio = radio
        self.lat = config.lat
        self.lng = config.lng
        self.heading = 0.0
        self._grid: CoverageGrid | None = None
        self._algorithm: Algorithm | None = None
        self._cell_size_m = 50.0
        self._waypoint: Position | None = None
        self._waypoint_pos: tuple[float, float] | None = None
        self._sensor_target_id: int | None = None
        self._claim_expiry: dict[int, float] = {}

    @property
    def grid(self) -> CoverageGrid | None:
        return self._grid

    def start(
        self,
        grid: CoverageGrid,
        start: Position,
        all_starts: list[Position],
        algorithm: Algorithm,
    ) -> None:
        """Initialise navigation for a new mission."""
        self._grid = grid
        self._cell_size_m = grid.cell_size_m
        self._algorithm = algorithm
        algorithm.setup(grid, start, all_starts)

    def redirect_to_sensor(self, sensor_id: int, sensor_lat: float, sensor_lng: float) -> None:
        """Interrupt the current traversal to navigate toward a nearby sensor."""
        if self._sensor_target_id is not None or self._grid is None:
            return
        self._sensor_target_id = sensor_id
        self._abandon_waypoint()
        self._navigate_to(self._grid.coords_to_cell(sensor_lat, sensor_lng))

    def should_collect_sensor(self, sensor_id: int) -> bool:
        """Ask the algorithm whether this sensor should be collected."""
        if self._algorithm is None:
            return True
        return self._algorithm.should_collect_sensor(sensor_id)

    def is_sensor_found(self, lat: float, lng: float) -> bool:
        """Return True if the local map already shows this sensor's cell as collected."""
        if self._grid is None:
            return False
        return self._grid.get(self._grid.coords_to_cell(lat, lng)) >= CellState.SENSOR_FOUND

    def tick_exploring(self) -> ExploringStep:
        if self._grid is None or self._algorithm is None:
            return ExploringStep()

        if self._waypoint is None:
            nxt = self._algorithm.next_waypoint(self._grid, (self.lat, self.lng))
            if nxt is None:
                return ExploringStep(done=True)
            self._navigate_to(nxt)

        target_lat, target_lng = self._waypoint_pos
        step = self._config.speed_m_s * (self._config.tick_ms / 1000)

        if distance_m(self.lat, self.lng, target_lat, target_lng) <= step:
            return self._arrive_at_waypoint(target_lat, target_lng)

        self.heading = heading_deg(self.lat, self.lng, target_lat, target_lng)
        self.lat, self.lng = step_toward(self.lat, self.lng, target_lat, target_lng, step)
        return ExploringStep()

    def tick_returning(self, base_lat: float, base_lng: float) -> bool:
        """Move one step toward base. Returns True when arrived."""
        step = self._config.speed_m_s * (self._config.tick_ms / 1000)
        if distance_m(self.lat, self.lng, base_lat, base_lng) <= step:
            self.lat, self.lng = base_lat, base_lng
            return True
        self.heading = heading_deg(self.lat, self.lng, base_lat, base_lng)
        self.lat, self.lng = step_toward(self.lat, self.lng, base_lat, base_lng, step)
        return False

    def on_cell_update(self, cell_index: int, state: CellState, validity: int) -> None:
        """Apply a cell-state update received from a peer DENM.

        CLAIMED cells are marked so the traversal skips them.
        VISITED/SENSOR_FOUND cells additionally cancel any in-progress
        navigation to that cell — the peer has already covered it.
        After the grid is updated the Algorithm hook is called so implementations
        can react (e.g. replan the path).
        """
        if self._grid is None:
            return
        try:
            pos = self._grid.cell_from_index(cell_index)
            if state > self._grid.get(pos):
                self._grid.set(pos, state)
                if self._waypoint == pos and state >= CellState.VISITED:
                    self._abandon_waypoint()
                if self._algorithm is not None:
                    self._algorithm.on_cell_update(self._grid, pos, state)
            if state == CellState.CLAIMED:
                self._claim_expiry[cell_index] = time.monotonic() + validity
            elif cell_index in self._claim_expiry:
                del self._claim_expiry[cell_index]
        except (IndexError, ValueError):
            pass

    def expire_claims(self) -> None:
        """Revert CLAIMED cells whose validity has lapsed back to UNKNOWN."""
        if self._grid is None or not self._claim_expiry:
            return
        now = time.monotonic()
        expired = [idx for idx, exp in self._claim_expiry.items() if now >= exp]
        for cell_index in expired:
            del self._claim_expiry[cell_index]
            pos = self._grid.cell_from_index(cell_index)
            if self._grid.get(pos) == CellState.CLAIMED:
                self._grid.set(pos, CellState.UNKNOWN)

    # ── Private helpers ────────────────────────────────────────────────────

    def _navigate_to(self, pos: Position) -> None:
        self._waypoint = pos
        self._waypoint_pos = self._grid.cell_to_coords(pos)
        if self._grid.get(pos) == CellState.UNKNOWN:
            self._grid.set(pos, CellState.CLAIMED)
            cell_lat, cell_lng = self._waypoint_pos
            validity = max(10, int(self._cell_size_m / self._config.speed_m_s * 4))
            self._radio.publish_cell_state(self._grid.cell_index(pos), CellState.CLAIMED, cell_lat, cell_lng, validity)

    def _abandon_waypoint(self) -> None:
        if self._waypoint is not None and self._grid is not None:
            if self._grid.get(self._waypoint) == CellState.CLAIMED:
                self._grid.set(self._waypoint, CellState.UNKNOWN)
        self._waypoint = None
        self._waypoint_pos = None

    def _arrive_at_waypoint(self, target_lat: float, target_lng: float) -> ExploringStep:
        self.lat, self.lng = target_lat, target_lng
        pos = self._waypoint
        if CellState.VISITED > self._grid.get(pos):
            self._grid.set(pos, CellState.VISITED)
            self._radio.publish_cell_state(self._grid.cell_index(pos), CellState.VISITED, target_lat, target_lng)
        print(f"Drone {self._config.drone_id} visited ({pos.row},{pos.col})", flush=True)
        self._waypoint = None
        self._waypoint_pos = None
        if self._sensor_target_id is not None:
            sensor_id = self._sensor_target_id
            self._sensor_target_id = None
            return ExploringStep(sensor_id=sensor_id)
        return ExploringStep()
