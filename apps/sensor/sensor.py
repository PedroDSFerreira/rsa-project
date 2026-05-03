import json
import os
import random
import time

import paho.mqtt.client as mqtt

from identity import SensorIdentity

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt-central")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


def _generate_reading(identity: SensorIdentity) -> dict:
    return {
        "sensor_id":   identity.station_id,
        "temperature": round(random.uniform(15.0, 35.0), 2),
        "humidity":    round(random.uniform(30.0, 90.0), 2),
        "co2":         round(random.uniform(400.0, 2000.0), 2),
        "lat":         identity.lat,
        "lng":         identity.lng,
        "timestamp":   time.time(),
    }


class SensorAgent:
    def __init__(self, identity: SensorIdentity, ip: str):
        self._identity = identity
        self._ip = ip
        self._reading = _generate_reading(identity)
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sensor-{identity.station_id}",
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def announce(self):
        c = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sensor-announce-{self._identity.station_id}",
        )
        c.connect(MQTT_HOST, MQTT_PORT)
        c.publish("sim/announce", json.dumps({
            "station_id":     self._identity.station_id,
            "mac":            self._identity.mac,
            "container_name": self._identity.container_name,
            "ip":             self._ip,
            "lat":            self._identity.lat,
            "lng":            self._identity.lng,
            "entity_type":    "sensor",
        }))
        c.disconnect()
        print(
            f"Sensor {self._identity.station_id} announced at"
            f" {self._ip} ({self._identity.lat}, {self._identity.lng})",
            flush=True,
        )

    def run(self):
        self._client.connect(MQTT_HOST, MQTT_PORT)
        self._client.loop_forever()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Sensor {self._identity.station_id} connected: {reason_code}", flush=True)
        client.subscribe("sensor/request_data")

    def _on_message(self, client, userdata, msg):
        self._client.publish("sensor/data_response", json.dumps(self._reading))
        print(f"Sensor {self._identity.station_id} responded to request", flush=True)
