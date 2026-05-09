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

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Sensor {self._identity.station_id} connected: {reason_code}", flush=True)
        client.subscribe(f"sensor/{self._identity.station_id}/request")
        client.publish(f"sim/announce/{self._identity.station_id}", json.dumps({
            "station_id":     self._identity.station_id,
            "mac":            self._identity.mac,
            "container_name": self._identity.container_name,
            "ip":             self._ip,
            "lat":            self._identity.lat,
            "lng":            self._identity.lng,
            "entity_type":    "sensor",
        }), retain=True)
        print(
            f"Sensor {self._identity.station_id} announced at"
            f" {self._ip} ({self._identity.lat}, {self._identity.lng})",
            flush=True,
        )

    def _on_message(self, client, userdata, msg):
        try:
            requester_id = json.loads(msg.payload)["requester_id"]
        except (json.JSONDecodeError, KeyError):
            return
        self._client.publish(f"sensor/{self._identity.station_id}/response/{requester_id}", json.dumps(self._reading))
        print(f"Sensor {self._identity.station_id} responded to drone {requester_id}", flush=True)

    def run(self):
        while True:
            try:
                self._client.connect(MQTT_HOST, MQTT_PORT)
                break
            except Exception as e:
                print(f"Sensor {self._identity.station_id} connect failed: {e} — retrying in 2s", flush=True)
                time.sleep(2)
        self._client.loop_forever()
