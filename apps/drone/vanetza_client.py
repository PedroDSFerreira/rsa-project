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
        import time as _time
        payload = {
            "generationDeltaTime": int(_time.time() * 1000) % 65536,
            "camParameters": {
                "basicContainer": {
                    "stationType": 10,
                    "referencePosition": {
                        "latitude": lat,
                        "longitude": lng,
                        "positionConfidenceEllipse": {
                            "semiMajorAxisLength": 50,
                            "semiMinorAxisLength": 50,
                            "semiMajorAxisOrientation": 0,
                        },
                        "altitude": {"altitudeValue": 0.0, "altitudeConfidence": 15},
                    },
                },
                "highFrequencyContainer": {
                    "basicVehicleContainerHighFrequency": {
                        "heading": {"headingValue": heading, "headingConfidence": 1},
                        "speed": {"speedValue": speed, "speedConfidence": 1},
                        "driveDirection": 0,
                        "vehicleLength": {"vehicleLengthValue": 3.0, "vehicleLengthConfidenceIndication": 0},
                        "vehicleWidth": 1.5,
                        "longitudinalAcceleration": {"value": 0.0, "confidence": 0},
                        "curvature": {"curvatureValue": 0, "curvatureConfidence": 7},
                        "curvatureCalculationMode": 0,
                        "yawRate": {"yawRateValue": 0.0, "yawRateConfidence": 8},
                    }
                },
            },
        }
        self._client.publish("vanetza/in/cam", json.dumps(payload))

    def publish_denm(
        self,
        lat: float,
        lng: float,
        sub_cause_code: int,
        cell_index: int = 0,
        station_id: int = 0,
        validity_duration: int = 60,
    ):
        import time as _time
        t = _time.time()
        payload = {
            "management": {
                "actionId": {
                    "originatingStationId": station_id,
                    "sequenceNumber": cell_index,
                },
                "detectionTime": t,
                "referenceTime": t,
                "eventPosition": {
                    "latitude": lat,
                    "longitude": lng,
                    "positionConfidenceEllipse": {
                        "semiMajorConfidence": 0,
                        "semiMinorConfidence": 0,
                        "semiMajorOrientation": 0,
                    },
                    "altitude": {"altitudeValue": 0, "altitudeConfidence": 1},
                },
                "validityDuration": validity_duration,
                "stationType": 10,
            },
            "situation": {
                "informationQuality": 7,
                "eventType": {
                    "ccAndScc": {"dangerousSituation97": sub_cause_code},
                },
            },
        }
        self._client.publish("vanetza/in/denm", json.dumps(payload))

    def connect(self):
        self._client.connect(LOCAL_HOST, LOCAL_PORT)
        self._client.loop_start()

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()
