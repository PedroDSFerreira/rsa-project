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


def _compute_drone_starts() -> list[dict]:
    """Assign each drone a starting grid position (top-left of its zone).

    Drones are ordered by ID (1001, 1002, …). Each one starts at the first
    row of its equally-divided horizontal band. The algorithm running on each
    drone infers its own zone boundary from the full list of start rows.
    """
    rows = math.ceil(SIM_HEIGHT_M / CELL_SIZE_M)
    base_size = rows // NUM_DRONES
    remainder = rows % NUM_DRONES
    starts = []
    row = 0
    for i in range(1, NUM_DRONES + 1):
        starts.append({"drone_id": 1000 + i, "row": row, "col": 0})
        row += base_size + (1 if i <= remainder else 0)
    return starts


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
            try:
                command = json.loads(msg.payload)
                algorithm = command.get("algorithm") or TRAVERSAL_ALGORITHM
            except (json.JSONDecodeError, AttributeError):
                algorithm = TRAVERSAL_ALGORITHM
            self._publish_sim_start(client, algorithm)

    def _publish_sim_start(self, client, algorithm: str):
        drone_starts = _compute_drone_starts()
        sim_start = {
            "map": {
                "sw_lat":      SIM_SW_LAT,
                "sw_lng":      SIM_SW_LNG,
                "width_m":     SIM_WIDTH_M,
                "height_m":    SIM_HEIGHT_M,
                "cell_size_m": CELL_SIZE_M,
            },
            "algorithm":    algorithm,
            "drone_starts": drone_starts,
        }
        client.publish("sim/start", json.dumps(sim_start), retain=True)
        print(f"Published sim/start: algorithm={algorithm}, {len(drone_starts)} drones", flush=True)

    def _on_local_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe("sim/base/data_delivery")
        print("Base station listening for data deliveries", flush=True)

    def _on_message(self, client, userdata, msg):
        payload = json.loads(msg.payload)
        drone_id = payload.get("drone_id")
        sensors = payload.get("data", [])
        print(f"Data delivery from drone {drone_id}: {len(sensors)} sensor(s)", flush=True)
        for entry in sensors:
            sensor_id = entry["sensor_id"]
            self._central.publish(
                f"sim/delivery/{sensor_id}",
                json.dumps({"sensor_id": sensor_id, "drone_id": drone_id}),
                retain=True,
            )
            print(f"Reported delivery: sensor {sensor_id}", flush=True)

    def run(self):
        self._central.connect(MQTT_CENTRAL_HOST, MQTT_CENTRAL_PORT)
        self._central.loop_start()

        self._local.connect("127.0.0.1", 1883)
        self._local.loop_forever()


if __name__ == "__main__":
    BaseStationAgent(ip=_own_ip()).run()
