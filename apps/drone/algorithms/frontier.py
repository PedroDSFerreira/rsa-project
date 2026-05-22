from __future__ import annotations

import math

from algorithms.base import Algorithm, register
from coverage_grid import CellState, CoverageGrid, Position

_NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1))


@register("frontier")
class FrontierTraversal(Algorithm):
    """Targets the nearest frontier cell across the full grid.

    A frontier cell is an UNKNOWN cell adjacent to at least one VISITED (or
    SENSOR_FOUND) cell.  When no frontier exists yet — i.e. at mission start
    when all cells are still UNKNOWN — the drone falls back to the nearest
    UNKNOWN cell, identical to greedy behaviour.
    """

    def setup(self, grid: CoverageGrid, start: Position, all_starts: list[Position]) -> None:
        pass

    def next_waypoint(self, grid: CoverageGrid, position: tuple[float, float]) -> Position | None:
        drone_pos = grid.coords_to_cell(*position)

        best_frontier: Position | None = None
        best_fallback: Position | None = None
        best_claimed: Position | None = None
        best_frontier_dist = math.inf
        best_fallback_dist = math.inf
        best_claimed_dist = math.inf

        for row in range(grid.rows):
            for col in range(grid.cols):
                pos = Position(row, col)
                state = grid.get(pos)
                if state >= CellState.VISITED:
                    continue
                dist = (pos.row - drone_pos.row) ** 2 + (pos.col - drone_pos.col) ** 2
                if state == CellState.UNKNOWN:
                    if _is_frontier(grid, pos):
                        if dist < best_frontier_dist:
                            best_frontier_dist = dist
                            best_frontier = pos
                    else:
                        if dist < best_fallback_dist:
                            best_fallback_dist = dist
                            best_fallback = pos
                else:  # CLAIMED by a peer — last resort in case they abandon it
                    if dist < best_claimed_dist:
                        best_claimed_dist = dist
                        best_claimed = pos

        return best_frontier or best_fallback or best_claimed


# ── Helpers ────────────────────────────────────────────────────────────────

def _is_frontier(grid: CoverageGrid, pos: Position) -> bool:
    for dr, dc in _NEIGHBOURS:
        r, c = pos.row + dr, pos.col + dc
        if 0 <= r < grid.rows and 0 <= c < grid.cols:
            if grid.get(Position(r, c)) >= CellState.VISITED:
                return True
    return False
