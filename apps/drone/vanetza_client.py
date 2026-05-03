import json

import paho.mqtt.client as mqtt

LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 1883


class VanetzaClient:
    def __init__(self, client_id: str):
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._cam_callbacks: list = []
        self._denm_callbacks: list = []
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe("vanetza/out/cam")
        client.subscribe("vanetza/out/denm")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            return
        if msg.topic == "vanetza/out/cam":
            for cb in self._cam_callbacks:
                cb(payload)
        elif msg.topic == "vanetza/out/denm":
            for cb in self._denm_callbacks:
                cb(payload)

    def on_cam(self, callback):
        self._cam_callbacks.append(callback)

    def on_denm(self, callback):
        self._denm_callbacks.append(callback)

    def publish_cam(self, lat: float, lng: float, heading: float, speed: float):
        payload = {
            "fields": {
                "cam": {
                    "camParameters": {
                        "basicContainer": {
                            "referencePosition": {
                                "latitude": lat,
                                "longitude": lng,
                            }
                        },
                        "highFrequencyContainer": {
                            "basicVehicleContainerHighFrequency": {
                                "heading": {"headingValue": int(heading * 10)},
                                "speed": {"speedValue": int(speed * 100)},
                            }
                        },
                    }
                }
            }
        }
        self._client.publish("vanetza/in/cam", json.dumps(payload))

    def publish_denm(self, lat: float, lng: float, sub_cause_code: int, validity_duration: int = 60):
        payload = {
            "fields": {
                "denm": {
                    "management": {
                        "eventPosition": {
                            "latitude": lat,
                            "longitude": lng,
                        },
                        "validityDuration": validity_duration,
                    },
                    "situation": {
                        "eventType": {
                            "causeCode": 0,
                            "subCauseCode": sub_cause_code,
                        }
                    },
                }
            }
        }
        self._client.publish("vanetza/in/denm", json.dumps(payload))

    def connect(self):
        self._client.connect(LOCAL_HOST, LOCAL_PORT)
        self._client.loop_start()

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()
