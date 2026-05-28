from dataclasses import dataclass, field


@dataclass
class EntityInfo:
    station_id: int
    entity_type: str
    lat: float
    lng: float
    container_name: str = ""


@dataclass
class SimState:
    meta: dict = field(default_factory=dict)
    entities: dict[int, EntityInfo] = field(default_factory=dict)
    links: list[list[int]] = field(default_factory=list)
    grid_map: dict = field(default_factory=dict)
    grid_cells: dict[int, int] = field(default_factory=dict)         # cell_index → state (1=CLAIMED, 2=VISITED, 3=SENSOR_FOUND)
    visit_counts: dict[int, int] = field(default_factory=dict)       # cell_index → number of distinct drones that visited
    cell_visitors: dict[int, set] = field(default_factory=dict)      # cell_index → set of originatingStationIds seen
    deliveries: dict[int, int] = field(default_factory=dict)         # sensor_id → number of times delivered
    algorithms: list[str] = field(default_factory=list)
    completed_drones: set[int] = field(default_factory=set)
    tick: int = 0


state = SimState()
