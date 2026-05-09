import json
import math
import os
import socket

import paho.mqtt.client as mqtt

STATION_ID = 1
CONTAINER_NAME = os.environ.get("CONTAINER_NAME", "base_station")
LAT = float(os.environ["VANETZA_LATITUDE"])
LNG = float(os.environ["VANETZA_LONGITUDE"])
MAC = os.environ["VANETZA_MAC_ADDRESS"]

MQTT_CENTRAL_HOST = os.getenv("MQTT_HOST", "mqtt-central")
MQTT_CENTRAL_PORT = int(os.getenv("MQTT_PORT", "1883"))

SIM_SW_LAT = float(os.environ["SIM_AREA_SW_LAT"])
SIM_SW_LNG = float(os.environ["SIM_AREA_SW_LNG"])
SIM_WIDTH_M = float(os.environ["SIM_AREA_WIDTH_M"])
SIM_HEIGHT_M = float(os.environ["SIM_AREA_HEIGHT_M"])
CELL_SIZE_M = float(os.environ["CELL_SIZE_M"])
NUM_DRONES = int(os.environ["NUM_DRONES"])
TRAVERSAL_ALGORITHM = os.getenv("TRAVERSAL_ALGORITHM", "boustrophedon")


def _own_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


def _compute_strips() -> list[dict]:
    rows = math.ceil(SIM_HEIGHT_M / CELL_SIZE_M)
    base_size = rows // NUM_DRONES
    remainder = rows % NUM_DRONES
    strips = []
    row = 0
    for i in range(1, NUM_DRONES + 1):
        size = base_size + (1 if i <= remainder else 0)
        strips.append({"drone_index": i, "row_min": row, "row_max": row + size - 1})
        row += size
    return strips


class BaseStationAgent:
    def __init__(self, ip: str):
        self._ip = ip

        self._central = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="base-station-central")
        self._central.on_connect = self._on_central_connect
        self._central.on_message = self._on_central_message

        self._local = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="base-station-local")
        self._local.on_connect = self._on_local_connect
        self._local.on_message = self._on_message

    def _on_central_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Base station connected to mqtt-central: {reason_code}", flush=True)
        client.subscribe("sim/command/start")
        client.publish(f"sim/announce/{STATION_ID}", json.dumps({
            "station_id":     STATION_ID,
            "mac":            MAC,
            "container_name": CONTAINER_NAME,
            "ip":             self._ip,
            "lat":            LAT,
            "lng":            LNG,
            "entity_type":    "base_station",
        }), retain=True)

    def _on_central_message(self, client, userdata, msg):
        if msg.topic == "sim/command/start":
            self._publish_sim_start(client)

    def _publish_sim_start(self, client):
        sim_start = {
            "map": {
                "sw_lat":      SIM_SW_LAT,
                "sw_lng":      SIM_SW_LNG,
                "width_m":     SIM_WIDTH_M,
                "height_m":    SIM_HEIGHT_M,
                "cell_size_m": CELL_SIZE_M,
            },
            "algorithm": TRAVERSAL_ALGORITHM,
            "strips":    _compute_strips(),
        }
        client.publish("sim/start", json.dumps(sim_start), retain=True)
        print(f"Published sim/start with {NUM_DRONES} strips", flush=True)

    def _on_local_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe("sim/base/data_delivery")
        print("Base station listening for data deliveries", flush=True)

    def _on_message(self, client, userdata, msg):
        payload = json.loads(msg.payload)
        print(f"Data delivery received: {json.dumps(payload)}", flush=True)

    def run(self):
        self._central.connect(MQTT_CENTRAL_HOST, MQTT_CENTRAL_PORT)
        self._central.loop_start()

        self._local.connect("127.0.0.1", 1883)
        self._local.loop_forever()


if __name__ == "__main__":
    BaseStationAgent(ip=_own_ip()).run()
