#!/bin/sh
set -e

CONTAINER_ID=$(cat /etc/hostname)
CONTAINER_NAME=$(curl -sf --unix-socket /var/run/docker.sock \
    "http://localhost/containers/${CONTAINER_ID}/json" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['Name'].lstrip('/'))")
INDEX=$(echo "$CONTAINER_NAME" | rev | cut -d'-' -f1 | rev)

export VANETZA_STATION_ID=$((10 + INDEX))
export VANETZA_STATION_TYPE=10
export VANETZA_MAC_ADDRESS="6e:06:e0:03:02:$(printf '%02x' "$INDEX")"
export VANETZA_INTERFACE=br0
export VANETZA_USE_HARDCODED_GPS=true
export VANETZA_CAM_PERIODICITY=500
export VANETZA_DENM_MQTT_TIME_ENABLED=true
export START_EMBEDDED_MOSQUITTO=true
export SUPPORT_MAC_BLOCKING=true
export VANETZA_REMOTE_MQTT_BROKER="${MQTT_HOST:-mqtt-central}"
export VANETZA_REMOTE_MQTT_PORT="${MQTT_PORT:-1883}"
export VANETZA_LATITUDE="${BASE_STATION_LAT:-40.630}"
export VANETZA_LONGITUDE="${BASE_STATION_LNG:--8.660}"
export DRONE_CONTAINER_NAME="$CONTAINER_NAME"

/entrypoint.sh &
sleep 5
exec python3 /app/main.py
