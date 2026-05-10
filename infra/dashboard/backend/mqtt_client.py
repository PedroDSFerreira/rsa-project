import json
import math
import os

import paho.mqtt.client as mqtt

from state import EntityInfo, state

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt-central")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

_client: mqtt.Client | None = None


def _on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe("sim/meta")
    client.subscribe("sim/announce/+")
    client.subscribe("sim/links")
    client.subscribe("sim/start")
    client.subscribe("+/vanetza/time/cam")
    client.subscribe("+/vanetza/time/denm")
    client.subscribe("+/vanetza/out/denm")
    client.subscribe("sensor/+/response/+")


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload)
    except json.JSONDecodeError:
        return

    topic = msg.topic

    if topic == "sim/meta":
        state.meta = payload

    elif topic.startswith("sim/announce/"):
        sid = payload["station_id"]
        state.entities[sid] = EntityInfo(
            station_id=sid,
            entity_type=payload["entity_type"],
            lat=payload["lat"],
            lng=payload["lng"],
            container_name=payload.get("container_name", ""),
        )

    elif topic == "sim/links":
        state.links = payload.get("connected", [])
        state.tick = payload.get("tick", state.tick)

    elif topic == "sim/start":
        m = payload.get("map", {})
        if m:
            state.grid_map = m

    elif "/vanetza/time/cam" in topic:
        try:
            sid = payload.get("stationID")
            entity = state.entities.get(sid)
            if not entity or entity.entity_type != "drone":
                return
            cam = payload.get("camParameters") or payload.get("fields", {}).get("cam", {}).get("camParameters", {})
            pos = cam["basicContainer"]["referencePosition"]
            entity.lat = pos["latitude"]
            entity.lng = pos["longitude"]
        except (KeyError, TypeError):
            pass

    elif "/vanetza/time/denm" in topic:
        try:
            encoded = payload["management"]["actionId"]["sequenceNumber"]
            cell_index, sub_cause = divmod(encoded, 4)
            new_state = sub_cause + 1
            if new_state > state.grid_cells.get(cell_index, 0):
                state.grid_cells[cell_index] = new_state
        except (KeyError, TypeError):
            pass

    elif topic.startswith("sensor/") and "/response/" in topic:
        try:
            sensor_id = int(topic.split("/")[1])
            sensor = state.entities.get(sensor_id)
            m = state.grid_map
            if sensor and m:
                meters_per_lat = 111000.0
                meters_per_lng = 111000.0 * math.cos(math.radians(m["sw_lat"]))
                cols = math.ceil(m["width_m"] / m["cell_size_m"])
                row = int((sensor.lat - m["sw_lat"]) * meters_per_lat / m["cell_size_m"])
                col = int((sensor.lng - m["sw_lng"]) * meters_per_lng / m["cell_size_m"])
                cell_index = row * cols + col
                state.grid_cells[cell_index] = 3  # SENSOR_FOUND
        except (KeyError, ValueError, TypeError):
            pass

    elif "/vanetza/out/denm" in topic:
        try:
            denm = payload.get("fields", {}).get("denm") or payload
            encoded = denm["management"]["actionId"]["sequenceNumber"]
            cell_index, sub_cause = divmod(encoded, 4)
            new_state = sub_cause + 1  # 0→1(CLAIMED), 1→2(VISITED), 2→3(SENSOR_FOUND)
            if new_state > state.grid_cells.get(cell_index, 0):
                state.grid_cells[cell_index] = new_state
        except (KeyError, TypeError):
            pass


def start():
    global _client
    _client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dashboard-backend")
    _client.on_connect = _on_connect
    _client.on_message = _on_message
    _client.connect(MQTT_HOST, MQTT_PORT)
    _client.loop_start()


def publish(topic: str, payload: str) -> None:
    if _client is not None:
        _client.publish(topic, payload)
