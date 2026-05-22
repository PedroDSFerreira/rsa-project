from __future__ import annotations

import math

from algorithms.base import Algorithm, register
from coverage_grid import CellState, CoverageGrid, Position


@register("greedy")
class GreedyNearestTraversal(Algorithm):
    """Visits the nearest UNKNOWN cell within the assigned zone at each step."""

    def __init__(self) -> None:
        self._row_min = 0
        self._row_max = 0

    def setup(self, grid: CoverageGrid, start: Position, all_starts: list[Position]) -> None:
        self._row_min = start.row
        self._row_max = _zone_end_row(start, all_starts, grid.rows)

    def next_waypoint(self, grid: CoverageGrid, position: tuple[float, float]) -> Position | None:
        drone_pos = grid.coords_to_cell(*position)
        best: Position | None = None
        best_dist = math.inf
        for row in range(self._row_min, self._row_max + 1):
            for col in range(grid.cols):
                pos = Position(row, col)
                if grid.get(pos) == CellState.UNKNOWN:
                    dist = (pos.row - drone_pos.row) ** 2 + (pos.col - drone_pos.col) ** 2
                    if dist < best_dist:
                        best_dist = dist
                        best = pos
        return best


# ── Helpers ────────────────────────────────────────────────────────────────

def _zone_end_row(start: Position, all_starts: list[Position], total_rows: int) -> int:
    higher = sorted(p.row for p in all_starts if p.row > start.row)
    return higher[0] - 1 if higher else total_rows - 1
