from __future__ import annotations

from algorithms.base import Traversal
from coverage_grid import CellState, CoverageGrid


class BoustrophedonTraversal(Traversal):
    """Covers a rectangular band of rows in a lawnmower (boustrophedon) pattern."""

    def __init__(self, row_min: int, row_max: int, cols: int):
        self._sequence = _build_sequence(row_min, row_max, cols)

    def next_waypoint(
        self,
        grid: CoverageGrid,
        position: tuple[float, float],
    ) -> tuple[int, int] | None:
        for row, col in self._sequence:
            if grid.get(row, col) == CellState.UNKNOWN:
                return row, col
        return None


def _build_sequence(row_min: int, row_max: int, cols: int) -> list[tuple[int, int]]:
    sequence = []
    for i, row in enumerate(range(row_min, row_max + 1)):
        col_range = range(cols) if i % 2 == 0 else range(cols - 1, -1, -1)
        for col in col_range:
            sequence.append((row, col))
    return sequence
