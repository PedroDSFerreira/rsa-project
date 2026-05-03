import json
import os
import socket

import paho.mqtt.client as mqtt

STATION_ID = 1
CONTAINER_NAME = "base_station"
LAT = float(os.environ["VANETZA_LATITUDE"])
LNG = float(os.environ["VANETZA_LONGITUDE"])
MAC = os.environ["VANETZA_MAC_ADDRESS"]

MQTT_CENTRAL_HOST = os.getenv("MQTT_HOST", "mqtt-central")
MQTT_CENTRAL_PORT = int(os.getenv("MQTT_PORT", "1883"))


def _own_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


class BaseStationAgent:
    def __init__(self, ip: str):
        self._ip = ip
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="base-station")
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Base station connected: {reason_code}", flush=True)
        client.subscribe("sim/base/data_delivery")

    def _on_message(self, client, userdata, msg):
        payload = json.loads(msg.payload)
        print(f"Received data delivery: {json.dumps(payload)}", flush=True)

    def announce(self):
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="base-station-announce")
        c.connect(MQTT_CENTRAL_HOST, MQTT_CENTRAL_PORT)
        c.publish("sim/announce", json.dumps({
            "station_id":     STATION_ID,
            "mac":            MAC,
            "container_name": CONTAINER_NAME,
            "ip":             self._ip,
            "lat":            LAT,
            "lng":            LNG,
            "entity_type":    "base_station",
        }))
        c.disconnect()
        print(f"Base station announced at {self._ip} ({LAT}, {LNG})", flush=True)

    def run(self):
        self.announce()
        self._client.connect("127.0.0.1", 1883)
        self._client.loop_forever()


if __name__ == "__main__":
    BaseStationAgent(ip=_own_ip()).run()
