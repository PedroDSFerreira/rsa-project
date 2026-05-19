from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DroneConfig:
    drone_id: int
    lat: float
    lng: float
    mac: str
    container_name: str
    mqtt_host: str
    mqtt_port: int
    tick_ms: int
    speed_m_s: float
    collection_time_s: float

    @classmethod
    def from_env(cls) -> DroneConfig:
        return cls(
            drone_id=int(os.environ["VANETZA_STATION_ID"]),
            lat=float(os.environ["VANETZA_LATITUDE"]),
            lng=float(os.environ["VANETZA_LONGITUDE"]),
            mac=os.environ["VANETZA_MAC_ADDRESS"],
            container_name=os.environ["DRONE_CONTAINER_NAME"],
            mqtt_host=os.getenv("MQTT_HOST", "mqtt-central"),
            mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
            tick_ms=int(os.getenv("TICK_REAL_MS", "500")),
            speed_m_s=float(os.getenv("DRONE_SPEED_M_S", "5.0")),
            collection_time_s=float(os.getenv("DRONE_COLLECTION_TIME_S", "3.0")),
        )
