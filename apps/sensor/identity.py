import http.client
import json
import math
import os
import random
import socket
from dataclasses import dataclass


@dataclass(frozen=True)
class SensorIdentity:
    station_id: int
    mac: str
    container_name: str
    lat: float
    lng: float


def resolve() -> SensorIdentity:
    name = _container_name()
    index = int(name.rsplit("-", 1)[-1])
    station_id = 2000 + index
    mac = f"6e:06:e0:03:01:{index:02x}"
    lat, lng = _compute_gps(station_id)
    return SensorIdentity(station_id=station_id, mac=mac, container_name=name, lat=lat, lng=lng)


def own_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


def _container_name() -> str:
    with open("/etc/hostname") as f:
        container_id = f.read().strip()
    conn = _UnixHTTPConnection()
    conn.request("GET", f"/containers/{container_id}/json")
    data = json.loads(conn.getresponse().read())
    return data["Name"].lstrip("/")


def _compute_gps(station_id: int) -> tuple[float, float]:
    seed = int(os.getenv("SIM_RANDOM_SEED", "42")) + station_id
    rng = random.Random(seed)
    origin_lat = float(os.getenv("SIM_AREA_SW_LAT", "40.630"))
    origin_lng = float(os.getenv("SIM_AREA_SW_LNG", "-8.660"))
    width_m = float(os.getenv("SIM_AREA_WIDTH_M", "1000"))
    height_m = float(os.getenv("SIM_AREA_HEIGHT_M", "1000"))
    lat = origin_lat + rng.uniform(0.05, 0.95) * height_m / 111000
    lng = origin_lng + rng.uniform(0.05, 0.95) * width_m / (111000 * math.cos(math.radians(origin_lat)))
    return round(lat, 6), round(lng, 6)


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("localhost")

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect("/var/run/docker.sock")
