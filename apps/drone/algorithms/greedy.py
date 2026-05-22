from __future__ import annotations

import math

from algorithms.base import Algorithm, register
from coverage_grid import CellState, CoverageGrid, Position


@register("greedy")
class GreedyNearestTraversal(Algorithm):
    """Visits the nearest UNKNOWN cell in the full grid at each step.
    """

    def setup(self, grid: CoverageGrid, start: Position, all_starts: list[Position]) -> None:
        pass

    def next_waypoint(self, grid: CoverageGrid, position: tuple[float, float]) -> Position | None:
        drone_pos = grid.coords_to_cell(*position)
        best: Position | None = None
        best_dist = math.inf
        for row in range(grid.rows):
            for col in range(grid.cols):
                pos = Position(row, col)
                if grid.get(pos) == CellState.UNKNOWN:
                    dist = (pos.row - drone_pos.row) ** 2 + (pos.col - drone_pos.col) ** 2
                    if dist < best_dist:
                        best_dist = dist
                        best = pos
        return best
