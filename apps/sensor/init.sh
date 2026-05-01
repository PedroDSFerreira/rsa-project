#!/bin/sh
set -e

CONTAINER_ID=$(cat /etc/hostname)
CONTAINER_NAME=$(curl -sf --unix-socket /var/run/docker.sock \
    "http://localhost/containers/${CONTAINER_ID}/json" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['Name'].lstrip('/'))")
INDEX=$(echo "$CONTAINER_NAME" | rev | cut -d'-' -f1 | rev)

export VANETZA_STATION_ID=$((20 + INDEX))
export VANETZA_STATION_TYPE=10
export VANETZA_MAC_ADDRESS="6e:06:e0:03:01:$(printf '%02x' "$INDEX")"
export VANETZA_INTERFACE=br0
export VANETZA_USE_HARDCODED_GPS=true
export VANETZA_CAM_PERIODICITY=2000
export START_EMBEDDED_MOSQUITTO=true
export SUPPORT_MAC_BLOCKING=true
export VANETZA_REMOTE_MQTT_BROKER="${MQTT_CENTRAL_HOST:-mqtt-central}"
export VANETZA_REMOTE_MQTT_PORT="${MQTT_CENTRAL_PORT:-1883}"

GPS=$(python3 - <<'EOF'
import os, random, math
seed = int(os.getenv('RANDOM_SEED', '42')) + int(os.environ['VANETZA_STATION_ID'])
rng = random.Random(seed)
origin_lat = float(os.getenv('MAP_ORIGIN_LAT', '40.630'))
origin_lng = float(os.getenv('MAP_ORIGIN_LNG', '-8.660'))
width_m  = float(os.getenv('MAP_WIDTH_M',  '1000'))
height_m = float(os.getenv('MAP_HEIGHT_M', '1000'))
lat = origin_lat + rng.uniform(0.05, 0.95) * height_m / 111000
lng = origin_lng + rng.uniform(0.05, 0.95) * width_m / (111000 * math.cos(math.radians(origin_lat)))
print(f"{lat:.6f} {lng:.6f}")
EOF
)
export VANETZA_LATITUDE=$(echo "$GPS" | cut -d' ' -f1)
export VANETZA_LONGITUDE=$(echo "$GPS" | cut -d' ' -f2)

export SENSOR_CONTAINER_NAME="$CONTAINER_NAME"

/entrypoint.sh &
sleep 5
exec python3 /app/main.py
