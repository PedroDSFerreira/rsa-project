class Entity:
    def __init__(self, station_id: int, container_name: str, mac: str, lat: float, lng: float):
        self.station_id = station_id
        self.container_name = container_name
        self.mac = mac
        self.lat = lat
        self.lng = lng
