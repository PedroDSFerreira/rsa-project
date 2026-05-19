from __future__ import annotations

import math
import socket

METERS_PER_LAT = 111000.0


def own_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


def meters_per_lng(lat: float) -> float:
    return METERS_PER_LAT * math.cos(math.radians(lat))


def distance_m(lat: float, lng: float, tlat: float, tlng: float) -> float:
    dlat = (tlat - lat) * METERS_PER_LAT
    dlng = (tlng - lng) * meters_per_lng(lat)
    return math.hypot(dlat, dlng)


def heading_deg(lat: float, lng: float, tlat: float, tlng: float) -> float:
    dlat = (tlat - lat) * METERS_PER_LAT
    dlng = (tlng - lng) * meters_per_lng(lat)
    return math.degrees(math.atan2(dlng, dlat)) % 360


def step_toward(lat: float, lng: float, tlat: float, tlng: float, step_m: float) -> tuple[float, float]:
    dlat = (tlat - lat) * METERS_PER_LAT
    dlng = (tlng - lng) * meters_per_lng(lat)
    length = math.hypot(dlat, dlng)
    lat += (dlat / length) * step_m / METERS_PER_LAT
    lng += (dlng / length) * step_m / meters_per_lng(lat)
    return lat, lng
