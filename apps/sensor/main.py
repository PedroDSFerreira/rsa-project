import os
import json
import random
import time
import paho.mqtt.client as mqtt

SENSOR_ID  = int(os.environ["SENSOR_ID"])
SENSOR_LAT = float(os.environ["SENSOR_LAT"])
SENSOR_LNG = float(os.environ["SENSOR_LNG"])

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


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


def _on_connect(client, userdata, flags, reason_code, properties):
    print(f"Sensor {SENSOR_ID} connected: {reason_code}", flush=True)
    client.subscribe("sensor/request_data")


def _on_message(client, userdata, msg):
    client.publish("sensor/data_response", json.dumps(_payload))
    print(f"Sensor {SENSOR_ID} responded to request", flush=True)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sensor-{SENSOR_ID}")
client.on_connect = _on_connect
client.on_message = _on_message

client.connect(MQTT_HOST, MQTT_PORT)
print(f"Sensor {SENSOR_ID} ready at ({SENSOR_LAT}, {SENSOR_LNG})", flush=True)
client.loop_forever()
