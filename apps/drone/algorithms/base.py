from __future__ import annotations

from abc import ABC, abstractmethod

from coverage_grid import CellState, CoverageGrid, Position

_registry: dict[str, type["Algorithm"]] = {}


def register(name: str):
    """Class decorator that registers an Algorithm subclass under *name*."""

    def decorator(cls: type[Algorithm]) -> type[Algorithm]:
        _registry[name] = cls
        return cls

    return decorator


class Algorithm(ABC):
    """Base class for all coverage traversal algorithms.

    Each algorithm receives the full grid and this drone's starting Position.
    Zone boundaries, traversal order, and all internal state are managed
    entirely by the implementation — no strip concept leaks outside.

    Optional hooks (on_cell_update, should_collect_sensor) have sensible
    defaults so simple algorithms need only implement setup and next_waypoint.
    """

    @abstractmethod
    def setup(
        self,
        grid: CoverageGrid,
        start: Position,
        all_starts: list[Position],
    ) -> None:
        """Initialise the traversal plan for this drone.

        Args:
            grid: the full coverage grid (all cells UNKNOWN at call time).
            start: grid Position assigned to this drone as its starting point.
            all_starts: starting Position of every drone in the mission,
                sorted by ascending row. Used to infer zone boundaries without
                the base station having to pre-compute them.
        """
        ...

    @abstractmethod
    def next_waypoint(
        self,
        grid: CoverageGrid,
        position: tuple[float, float],
    ) -> Position | None:
        """Return the next Position to visit, or None when the zone is fully covered."""
        ...

    def on_cell_update(self, grid: CoverageGrid, pos: Position, state: CellState) -> None:
        """Called after the grid is updated from a peer DENM.

        Override to react dynamically to new information — e.g. to skip a
        zone a peer has already covered, or to replan the traversal path.
        The grid has already been updated before this hook fires.
        """

    def should_collect_sensor(self, sensor_id: int) -> bool:
        """Whether this drone should collect data from a nearby sensor.

        Override to implement selective collection strategies.
        Default: always collect.
        """
        return True
