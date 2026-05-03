import json
import os

import paho.mqtt.client as mqtt

from state import EntityInfo, state

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt-central")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


def _on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe("sim/meta")
    client.subscribe("sim/announce")
    client.subscribe("sim/links")
    client.subscribe("+/vanetza/own/cam")


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload)
    except json.JSONDecodeError:
        return

    topic = msg.topic

    if topic == "sim/meta":
        state.meta = payload

    elif topic == "sim/announce":
        sid = payload["station_id"]
        state.entities[sid] = EntityInfo(
            station_id=sid,
            entity_type=payload["entity_type"],
            mac=payload["mac"],
            container_name=payload["container_name"],
            ip=payload["ip"],
            lat=payload["lat"],
            lng=payload["lng"],
        )

    elif topic == "sim/links":
        state.links = payload.get("connected", [])
        state.tick = payload.get("tick", state.tick)

    elif "/vanetza/own/cam" in topic:
        try:
            sid = payload["stationID"]
            pos = payload["fields"]["cam"]["camParameters"]["basicContainer"]["referencePosition"]
            if sid in state.entities:
                state.entities[sid].lat = pos["latitude"]
                state.entities[sid].lng = pos["longitude"]
        except KeyError:
            pass


def start():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dashboard-backend")
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_start()
