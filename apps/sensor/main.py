import os
import json
import random
import socket
import time
import paho.mqtt.client as mqtt

SENSOR_ID  = int(os.environ["VANETZA_STATION_ID"])
SENSOR_LAT = float(os.environ["VANETZA_LATITUDE"])
SENSOR_LNG = float(os.environ["VANETZA_LONGITUDE"])
SENSOR_MAC = os.environ["VANETZA_MAC_ADDRESS"]
CONTAINER_NAME = os.environ["SENSOR_CONTAINER_NAME"]

MQTT_CENTRAL_HOST = os.getenv("MQTT_HOST", "mqtt-central")
MQTT_CENTRAL_PORT = int(os.getenv("MQTT_PORT", "1883"))


def _own_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


def _generate_payload() -> dict:
    return {
        "sensor_id":   SENSOR_ID,
        "temperature": round(random.uniform(15.0, 35.0), 2),
        "humidity":    round(random.uniform(30.0, 90.0), 2),
        "co2":         round(random.uniform(400.0, 2000.0), 2),
        "lat":         SENSOR_LAT,
        "lng":         SENSOR_LNG,
        "timestamp":   time.time(),
    }


_payload = _generate_payload()


def _announce(ip: str):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sensor-announce-{SENSOR_ID}")
    c.connect(MQTT_CENTRAL_HOST, MQTT_CENTRAL_PORT)
    c.publish("sim/announce", json.dumps({
        "station_id":     SENSOR_ID,
        "mac":            SENSOR_MAC,
        "container_name": CONTAINER_NAME,
        "ip":             ip,
        "lat":            SENSOR_LAT,
        "lng":            SENSOR_LNG,
        "entity_type":    "sensor",
    }))
    c.disconnect()


def _on_connect(client, userdata, flags, reason_code, properties):
    print(f"Sensor {SENSOR_ID} connected: {reason_code}", flush=True)
    client.subscribe("sensor/request_data")


def _on_message(client, userdata, msg):
    client.publish("sensor/data_response", json.dumps(_payload))
    print(f"Sensor {SENSOR_ID} responded to request", flush=True)


ip = _own_ip()
_announce(ip)
print(f"Sensor {SENSOR_ID} announced at {ip} ({SENSOR_LAT}, {SENSOR_LNG})", flush=True)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sensor-{SENSOR_ID}")
client.on_connect = _on_connect
client.on_message = _on_message
client.connect("127.0.0.1", 1883)
client.loop_forever()
