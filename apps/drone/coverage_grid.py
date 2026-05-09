import math
from enum import IntEnum


class CellState(IntEnum):
    UNKNOWN = 0
    CLAIMED = 1
    VISITED = 2
    SENSOR_FOUND = 3


class CoverageGrid:
    def __init__(self, sw_lat: float, sw_lng: float, width_m: float, height_m: float, cell_size_m: float):
        self._sw_lat = sw_lat
        self._sw_lng = sw_lng
        self._width_m = width_m
        self._height_m = height_m
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

    def get(self, row: int, col: int) -> CellState:
        return self._cells[row][col]

    def set(self, row: int, col: int, state: CellState) -> None:
        self._cells[row][col] = state

    def coords_to_cell(self, lat: float, lng: float) -> tuple[int, int]:
        meters_per_lat = 111000.0
        meters_per_lng = 111000.0 * math.cos(math.radians(self._sw_lat))
        row = int((lat - self._sw_lat) * meters_per_lat / self._cell_size_m)
        col = int((lng - self._sw_lng) * meters_per_lng / self._cell_size_m)
        row = max(0, min(self._rows - 1, row))
        col = max(0, min(self._cols - 1, col))
        return row, col

    def cell_to_coords(self, row: int, col: int) -> tuple[float, float]:
        meters_per_lat = 111000.0
        meters_per_lng = 111000.0 * math.cos(math.radians(self._sw_lat))
        lat = self._sw_lat + (row + 0.5) * self._cell_size_m / meters_per_lat
        lng = self._sw_lng + (col + 0.5) * self._cell_size_m / meters_per_lng
        return lat, lng

    def cell_index(self, row: int, col: int) -> int:
        return row * self._cols + col

    def cell_from_index(self, index: int) -> tuple[int, int]:
        return divmod(index, self._cols)
