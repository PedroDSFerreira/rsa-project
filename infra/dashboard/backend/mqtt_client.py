import json
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
            cam = payload.get("camParameters") or payload.get("fields", {}).get("cam", {}).get("camParameters", {})
            pos = cam["basicContainer"]["referencePosition"]
            if sid and sid in state.entities:
                state.entities[sid].lat = pos["latitude"]
                state.entities[sid].lng = pos["longitude"]
        except (KeyError, TypeError):
            pass

    elif "/vanetza/time/denm" in topic:
        try:
            cell_index = payload["management"]["actionId"]["sequenceNumber"]
            sub_cause = payload["situation"]["eventType"]["ccAndScc"].get("dangerousSituation97")
            if sub_cause is None:
                return
            new_state = sub_cause + 1
            if new_state > state.grid_cells.get(cell_index, 0):
                state.grid_cells[cell_index] = new_state
        except (KeyError, TypeError):
            pass

    elif "/vanetza/out/denm" in topic:
        try:
            denm = payload.get("fields", {}).get("denm") or payload
            cell_index = denm["management"]["actionId"]["sequenceNumber"]
            sub_cause = denm["situation"]["eventType"]["ccAndScc"].get("dangerousSituation97")
            if sub_cause is None:
                return
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
