from dataclasses import dataclass, field


@dataclass
class EntityInfo:
    station_id: int
    entity_type: str
    lat: float
    lng: float


@dataclass
class SimState:
    meta: dict = field(default_factory=dict)
    entities: dict[int, EntityInfo] = field(default_factory=dict)
    links: list[list[int]] = field(default_factory=list)
    tick: int = 0


state = SimState()
