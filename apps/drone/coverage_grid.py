from __future__ import annotations

import math
from enum import IntEnum
from typing import NamedTuple


class Position(NamedTuple):
    """A cell address in the coverage grid."""
    row: int
    col: int


class CellState(IntEnum):
    UNKNOWN = 0
    CLAIMED = 1
    VISITED = 2
    SENSOR_FOUND = 3


class CoverageGrid:
    def __init__(self, sw_lat: float, sw_lng: float, width_m: float, height_m: float, cell_size_m: float):
        self._sw_lat = sw_lat
        self._sw_lng = sw_lng
        self._cell_size_m = cell_size_m
        self._rows = math.ceil(height_m / cell_size_m)
        self._cols = math.ceil(width_m / cell_size_m)
        self._cells: list[list[CellState]] = [
            [CellState.UNKNOWN] * self._cols for _ in range(self._rows)
        ]

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def cols(self) -> int:
        return self._cols

    @property
    def cell_size_m(self) -> float:
        return self._cell_size_m

    def get(self, pos: Position) -> CellState:
        return self._cells[pos.row][pos.col]

    def set(self, pos: Position, state: CellState) -> None:
        self._cells[pos.row][pos.col] = state

    def all_cells(self) -> list[list[int]]:
        """Return a snapshot of all cell states as a 2-D list of ints."""
        return [[int(s) for s in row] for row in self._cells]

    def coords_to_cell(self, lat: float, lng: float) -> Position:
        meters_per_lat = 111000.0
        meters_per_lng = 111000.0 * math.cos(math.radians(self._sw_lat))
        row = int((lat - self._sw_lat) * meters_per_lat / self._cell_size_m)
        col = int((lng - self._sw_lng) * meters_per_lng / self._cell_size_m)
        row = max(0, min(self._rows - 1, row))
        col = max(0, min(self._cols - 1, col))
        return Position(row, col)

    def cell_to_coords(self, pos: Position) -> tuple[float, float]:
        meters_per_lat = 111000.0
        meters_per_lng = 111000.0 * math.cos(math.radians(self._sw_lat))
        lat = self._sw_lat + (pos.row + 0.5) * self._cell_size_m / meters_per_lat
        lng = self._sw_lng + (pos.col + 0.5) * self._cell_size_m / meters_per_lng
        return lat, lng

    def cell_index(self, pos: Position) -> int:
        return pos.row * self._cols + pos.col

    def cell_from_index(self, index: int) -> Position:
        row, col = divmod(index, self._cols)
        return Position(row, col)
