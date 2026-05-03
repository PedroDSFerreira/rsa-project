VANETZA_TYPES = frozenset({"drone", "base_station"})


class Entity:
    def __init__(self, station_id: int, container_name: str, mac: str, lat: float, lng: float, entity_type: str):
        self.station_id = station_id
        self.container_name = container_name
        self.mac = mac
        self.lat = lat
        self.lng = lng
        self.entity_type = entity_type

    @property
    def has_vanetza(self) -> bool:
        return self.entity_type in VANETZA_TYPES
