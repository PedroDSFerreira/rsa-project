from __future__ import annotations

import math

from algorithms.base import Traversal
from coverage_grid import CellState, CoverageGrid


class GreedyNearestTraversal(Traversal):
    """Visits the nearest UNKNOWN cell greedily, optionally restricted to a row band."""

    def __init__(self, row_min: int | None = None, row_max: int | None = None):
        self._row_min = row_min
        self._row_max = row_max

    def next_waypoint(
        self,
        grid: CoverageGrid,
        position: tuple[float, float],
    ) -> tuple[int, int] | None:
        drone_row, drone_col = grid.coords_to_cell(*position)
        best: tuple[int, int] | None = None
        best_dist = math.inf
        row_start = self._row_min if self._row_min is not None else 0
        row_end = self._row_max + 1 if self._row_max is not None else grid.rows
        for row in range(row_start, row_end):
            for col in range(grid.cols):
                if grid.get(row, col) == CellState.UNKNOWN:
                    dist = (row - drone_row) ** 2 + (col - drone_col) ** 2
                    if dist < best_dist:
                        best_dist = dist
                        best = (row, col)
        return best
