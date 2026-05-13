from __future__ import annotations

from abc import ABC, abstractmethod

from coverage_grid import CoverageGrid


class Traversal(ABC):
    @abstractmethod
    def next_waypoint(
        self,
        grid: CoverageGrid,
        position: tuple[float, float],
    ) -> tuple[int, int] | None:
        """Return the next (row, col) cell to visit, or None when the area is fully covered."""
        ...
