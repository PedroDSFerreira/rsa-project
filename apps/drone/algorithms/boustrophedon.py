from __future__ import annotations

from algorithms.base import Algorithm
from coverage_grid import CellState, CoverageGrid, Position


class BoustrophedonTraversal(Algorithm):
    """Covers the assigned zone in a lawnmower (boustrophedon) pattern.

    The zone end row is derived at setup time from the drone's starting Position
    and the starting Positions of all other drones — no strip concept is exposed
    externally.
    """

    def __init__(self) -> None:
        self._sequence: list[Position] = []

    def setup(self, grid: CoverageGrid, start: Position, all_starts: list[Position]) -> None:
        end_row = _zone_end_row(start, all_starts, grid.rows)
        self._sequence = _build_sequence(start.row, end_row, grid.cols)

    def next_waypoint(self, grid: CoverageGrid, position: tuple[float, float]) -> Position | None:
        for pos in self._sequence:
            if grid.get(pos) == CellState.UNKNOWN:
                return pos
        return None


# ── Helpers ────────────────────────────────────────────────────────────────

def _zone_end_row(start: Position, all_starts: list[Position], total_rows: int) -> int:
    """Last row this drone owns: one row before the next drone's start row."""
    higher = sorted(p.row for p in all_starts if p.row > start.row)
    return higher[0] - 1 if higher else total_rows - 1


def _build_sequence(row_min: int, row_max: int, cols: int) -> list[Position]:
    sequence = []
    for i, row in enumerate(range(row_min, row_max + 1)):
        col_range = range(cols) if i % 2 == 0 else range(cols - 1, -1, -1)
        for col in col_range:
            sequence.append(Position(row, col))
    return sequence
