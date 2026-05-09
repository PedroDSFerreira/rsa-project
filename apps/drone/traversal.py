from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from coverage_grid import CellState, CoverageGrid


@dataclass(frozen=True)
class Strip:
    row_min: int
    row_max: int  # inclusive


class Traversal(ABC):
    @abstractmethod
    def next_waypoint(
        self,
        grid: CoverageGrid,
        drone_pos: tuple[float, float],
        strip: Strip,
    ) -> tuple[int, int] | None:
        ...


class BoustrophedonTraversal(Traversal):
    def __init__(self, strip: Strip, cols: int):
        self._sequence = _boustrophedon_sequence(strip, cols)

    def next_waypoint(
        self,
        grid: CoverageGrid,
        drone_pos: tuple[float, float],
        strip: Strip,
    ) -> tuple[int, int] | None:
        for row, col in self._sequence:
            if grid.get(row, col) == CellState.UNKNOWN:
                return row, col
        return None


class GreedyNearestTraversal(Traversal):
    def next_waypoint(
        self,
        grid: CoverageGrid,
        drone_pos: tuple[float, float],
        strip: Strip,
    ) -> tuple[int, int] | None:
        drone_row, drone_col = grid.coords_to_cell(*drone_pos)
        best: tuple[int, int] | None = None
        best_dist = math.inf
        for row in range(grid.rows):
            for col in range(grid.cols):
                if grid.get(row, col) == CellState.UNKNOWN:
                    dist = (row - drone_row) ** 2 + (col - drone_col) ** 2
                    if dist < best_dist:
                        best_dist = dist
                        best = (row, col)
        return best


def make_traversal(algorithm: str, strip: Strip, cols: int) -> Traversal:
    if algorithm == "greedy":
        return GreedyNearestTraversal()
    return BoustrophedonTraversal(strip, cols)


def _boustrophedon_sequence(strip: Strip, cols: int) -> list[tuple[int, int]]:
    sequence = []
    for i, row in enumerate(range(strip.row_min, strip.row_max + 1)):
        col_range = range(cols) if i % 2 == 0 else range(cols - 1, -1, -1)
        for col in col_range:
            sequence.append((row, col))
    return sequence
