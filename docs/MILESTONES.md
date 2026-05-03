# Implementation Milestones

Each milestone produces a **testable, runnable state** of the system. Later milestones build on earlier ones without breaking them.

---

## M1 — Docker Network + Vanetza-NAP Baseline

**Goal:** Two vanetza-nap containers exchange CAM messages on the virtual ITS-G5 network. Confirm the communication stack works before writing any application code.

### Tasks
- [x] Create `docker-compose.dev.yml` with two vanetza-nap containers (`node-a`, `node-b`) on `vanetzalan0`
- [x] Configure unique `VANETZA_STATION_ID`, `VANETZA_MAC_ADDRESS`, static IPs, `START_EMBEDDED_MOSQUITTO=true`, `SUPPORT_MAC_BLOCKING=true`
- [x] Add `mqtt-central` (Mosquitto) container; configure both vanetza nodes with `VANETZA_REMOTE_MQTT_BROKER=mqtt-central`
- [x] Verify CAM exchange: subscribe to `vanetza/out/cam` on `node-a`'s local broker and confirm CAMs from `node-b` arrive

### Acceptance Test
```bash
# In one terminal: subscribe on node-a's broker
docker exec node-a mosquitto_sub -t "vanetza/out/cam" -v

# In another: trigger a manual CAM from node-b
docker exec node-b mosquitto_pub -t "vanetza/in/cam" -f /examples/in_cam.json

# Expected: decoded CAM JSON appears in node-a's subscription
```

---

## M2 — ProximityManager: MAC Blocking

**Goal:** A Python service reads simulated positions and dynamically blocks/unblocks MAC addresses. Verify that communication is physically gated by proximity.

### Tasks
- [x] Create `proximity_manager/` with `Dockerfile`, `requirements.txt` (`paho-mqtt`, `docker`)
- [x] Implement `proximity.py`: connectivity matrix, `block(container, mac)` / `unblock(container, mac)` via Docker SDK
- [x] Implement `main.py`: read config from env vars, subscribe to `mqtt-central` `vanetza/out/cam` for drone positions, compute haversine distances each tick, call `proximity.py`
- [x] Publish `sim/meta` (retained) to `mqtt-central` on startup: `{ "map": {...}, "num_drones": N, "num_sensors": M }`
- [x] Publish `sim/links` each tick: `{ "connected": [[id_a, id_b], ...], "tick": N }`
- [x] Start all containers with all MACs fully blocked (isolated by default)
- [x] Add ProximityManager to `docker-compose.dev.yml` with Docker socket mounted

### Acceptance Test
```bash
# node-a and node-b start blocked. node-a subscribes to vanetza/out/cam.
# Manually publish a position CAM for node-b placing it far away.
# → no messages received on node-a.
# Publish a new CAM placing node-b within DRONE_RANGE_M of node-a.
# → ProximityManager calls unblock, node-a starts receiving CAMs from node-b.
# Move node-b away again → blocked again.
```

---

## M3 — Sensor Entity

**Goal:** A sensor container self-assigns its identity at startup, generates synthetic data, announces itself, and serves data to any requester.

### Tasks
- [x] Create `apps/sensor/` with `Dockerfile`, `requirements.txt`
- [x] Rework `Dockerfile` to extend `ghcr.io/nap-it/vanetza-nap:latest` (add Python + app; single bundled image)
- [x] Add `entrypoint.sh`: query Docker socket to extract replica index N, compute `station_id = 20+N`, `MAC = 6e:06:e0:03:01:<N>`, random GPS position within map bounds (seeded by N); export as `VANETZA_*` env vars; start vanetza-nap as background process
- [x] Implement `main.py`:
  - Read identity from env vars set by `entrypoint.sh`
  - Generate synthetic data payload at startup: `{ "temperature": ..., "humidity": ..., "co2": ..., "timestamp": ... }`
  - Publish `sim/announce` to `mqtt-central` with `{station_id, mac, container_name, ip, lat, lng, entity_type: "sensor"}`
  - Subscribe to `sensor/request_data` on local broker (port 1883)
  - Reply with payload on `sensor/data_response` when a request arrives
- [x] Update `docker-compose.dev.yml`: replace `sensor-1`+`sensor-1-app` pair with a single `sensor` service using `deploy.replicas`; mount Docker socket; pass map bounds as env vars
- [x] Update `proximity_manager/main.py`: replace `static_nodes` pre-population with `sim/announce` discovery; start tick loop only after all expected entities have announced
- [x] ProximityManager skips MAC blocking for sensors (no vanetza/`br0`); `entity_type` tracked on `Entity`; `ConnectivityMatrix.update` takes `Entity` objects

### Acceptance Test
```bash
# Start stack; sensor containers self-assign identity
docker compose up -d

# Subscribe on mqtt-central to see announcements
docker compose exec mqtt-central mosquitto_sub -h 127.0.0.1 -p 1883 -t "sim/announce" -C 2
# Expected: 2 JSON messages with station_id=21, station_id=22, unique MACs, random lat/lng

# Request data directly from a sensor using its announced IP
docker compose exec mqtt-central sh -c '
  mosquitto_sub -h <sensor_ip> -p 1883 -t "sensor/data_response" -C 1 -W 5 &
  sleep 0.2
  mosquitto_pub -h <sensor_ip> -p 1883 -t "sensor/request_data" -m "{\"requester_id\": 99}"
  wait
'
# Expected: JSON payload with temperature, humidity, co2
```

---

## M4 — Drone Core: Position Publishing + State Machine

**Goal:** A drone container self-assigns its identity at startup, announces itself, publishes its simulated position as CAMs, and runs a minimal state machine.

### Tasks
- [x] Create `apps/drone/` with `Dockerfile` extending `ghcr.io/nap-it/vanetza-nap:latest` (bundled single image)
- [x] Add `entrypoint.sh`: extract replica index N, compute `station_id = 10+N`, `MAC = 6e:06:e0:03:02:<N>`, start position = base station lat/lng; start vanetza-nap as background process
- [x] Implement `vanetza_client.py`: thin wrapper to publish/subscribe CAM and DENM on the local vanetza broker (127.0.0.1:1883)
- [x] Implement `main.py` with `DroneAgent`:
  - Publish `sim/announce` to `mqtt-central` with `{station_id, mac, container_name, ip, lat, lng, entity_type: "drone"}`
  - State machine with stubs: `IDLE → EXPLORING → COLLECTING → RETURNING → AT_BASE`
  - Wait for `IDLE` → `EXPLORING` signal (from base station via `sim/drone/{id}/mission` in M6; for now start immediately)
  - At each tick: publish CAM with current lat/lng/heading/speed
  - Subscribe to `vanetza/out/cam`: log incoming CAMs with `stationType`
  - Subscribe to `vanetza/out/denm`: log incoming DENMs
- [x] Add `drone` service to `docker-compose.dev.yml` with `deploy.replicas`, Docker socket mount, base station position env vars

### Acceptance Test
```bash
# Subscribe to mqtt-central, watch drone CAMs and announcements
docker compose exec mqtt-central mosquitto_sub -h 127.0.0.1 -p 1883 -t "sim/announce" -C 2
# Expected: 2 announce messages with station_id=11, station_id=12

docker compose exec mqtt-central mosquitto_sub -h 127.0.0.1 -p 1883 -t "+/vanetza/own/cam" -C 5
# Expected: CAMs from drones with updating lat/lng — ProximityManager adjusts connectivity
```

---

## M5 — Single-Drone Coverage: Grid + Boustrophedon + Sensor Collection

**Goal:** One drone autonomously sweeps its assigned strip, detects a sensor, collects data directly, and returns to base. Full end-to-end flow with one drone.

### Tasks
- [ ] Implement `coverage_grid.py`:
  - Grid class: 2D array of cells, each with state (`UNKNOWN`, `CLAIMED`, `VISITED`, `SENSOR_FOUND`)
  - `coords_to_cell(lat, lng)` and `cell_to_coords(row, col)` converters
  - `next_target(drone_pos, strip_bounds)`: boustrophedon path within strip; falls back to greedy nearest-unknown when strip is done
- [ ] Wire coverage into `DroneAgent`:
  - On `EXPLORING`: call `next_target`, set waypoint, publish DENM `subCauseCode=0` (claim), `sequenceNumber=cell_index`
  - On arrival at cell: publish DENM `subCauseCode=1` (visited), `sequenceNumber=cell_index`, mark `VISITED`
  - On receiving CAM with `stationType=10`: transition to `COLLECTING`
    - Look up sensor IP from `sim/announce/{id}` registry, connect to `{sensor_ip}:1883`, publish `sensor/request_data`, await `sensor/data_response`
    - Store payload, publish DENM `subCauseCode=2` (sensor collected), `sequenceNumber=cell_index`, mark `SENSOR_FOUND`
  - On `RETURNING`: navigate to base station GPS position
  - On receiving CAM with `stationType=15` while `RETURNING`: transition to `AT_BASE`
    - Look up base station IP from `sim/announce` registry, connect to `{base_ip}:1883`, publish collected data to `sim/base/data_delivery`
- [ ] Implement base station app stub (`apps/base_station/main.py`): subscribe `sim/base/data_delivery`, log received payloads

### Acceptance Test
```bash
docker compose up

# Observe logs:
# - Drone publishes CAMs with changing position
# - Drone publishes DENM claim/visited for each cell
# - When drone reaches sensor range → data collected (IP resolved from sim/announce)
# - Drone returns to base → base station logs received payload
```

---

## M6 — Multi-Drone: DENM Coordination + Grid Sync

**Goal:** Multiple drones share the area without duplicate work. DENMs from other drones update each drone's local grid. DTN grid sync fires when two drones first come into range.

### Tasks
- [ ] Base station app (`apps/base_station/main.py`):
  - At mission start, compute equal horizontal strip for each drone based on `CELL_SIZE_M`, `NUM_DRONES`, `SIM_AREA_*` env vars
  - Publish strip assignment to each drone via `sim/drone/{id}/mission` on `mqtt-central`
- [ ] Drone app: subscribe `sim/drone/{id}/mission` on startup, wait for strip assignment before starting `EXPLORING`
- [ ] Drone app: on receiving DENM from another drone:
  - `subCauseCode=0` → mark cell at `actionId.sequenceNumber` as `CLAIMED`
  - `subCauseCode=1` → mark cell as `VISITED`
  - `subCauseCode=2` → mark cell as `SENSOR_FOUND`
- [ ] Drone app: subscribe to `sim/grid_sync/{own_station_id}` on `mqtt-central`; on receipt merge peer grid into local grid (take highest-known state per cell)
- [ ] Drone app: implement DTN grid sync trigger
  - Track set of known peer station IDs from received CAMs
  - On first CAM from a previously-unseen peer: publish full local grid JSON to `sim/grid_sync/{peer_station_id}` on `mqtt-central`
- [ ] Handle stale claims: track DENM `detectionTime` + `validityDuration`; revert `CLAIMED` → `UNKNOWN` on expiry

### Acceptance Test
```bash
# Run with 2 drones, 5 sensors
# Observe: no cell is visited twice (no duplicate DENM subCauseCode=1 for the same position)
# Observe: when drones come into range of each other, grid sync DENMs fire
# Kill one drone mid-mission: its claimed cells should revert and be picked up by the other
```

---

## M7 — Base Station: Mission Completion + Cloud Upload

**Goal:** The base station manages the full mission lifecycle and uploads data when complete.

### Tasks
- [ ] Base station app: track mission completion
  - Monitor `vanetza/out/denm` on `mqtt-central`; count unique `SENSOR_FOUND` events
  - Detect when all drones are `AT_BASE` (no moving CAMs for N seconds) and all known sensors collected
  - Publish `sim/mission/complete` to `mqtt-central`
- [ ] Base station app: on `sim/mission/complete`, POST all collected sensor data to cloud endpoint (`CLOUD_ENDPOINT` env var)
- [ ] Add `mockserver` container to `docker-compose.infra.yml` (simple Python HTTP server that logs POST bodies) for local testing
- [ ] Replace mock with real endpoint via env var for demo

### Acceptance Test
```bash
# Run full simulation, watch mockserver logs
docker-compose logs mockserver

# Expected: one HTTP POST with all sensor payloads after all drones return
# Response should include a receipt/timestamp
```

---

## M8 — Dashboard

**Goal:** Real-time web UI showing drone positions, coverage grid progress, sensor discoveries, and connectivity links. Fully derived from the ETSI stream — no dependency on any mission controller.

### Tasks

#### Backend
- [ ] Create `dashboard/backend/` with FastAPI app
- [ ] Subscribe to `mqtt-central` on startup: `vanetza/out/cam`, `vanetza/out/denm`, `sim/links`, `sim/meta`
- [ ] Maintain `SimState` dataclass: drones, sensors (hidden until discovered), base, grid, links
- [ ] WebSocket endpoint `/ws`: push full state on connect, then diffs on each change
- [ ] REST endpoint `GET /state`: return current `SimState` as JSON (for debugging)

#### Frontend
- [ ] Create `dashboard/frontend/` (React + Vite + Leaflet.js)
- [ ] `SimContext.jsx`: WebSocket client, `useReducer` for state updates
- [ ] `MapView.jsx`: Leaflet map with:
  - Coverage grid overlay (color per cell state)
  - Drone markers with heading arrows (animated between ticks)
  - Sensor markers (hidden; appear only when `collected=true`)
  - Base station marker
  - Connectivity lines from `sim/links` (drawn between in-range pairs)
- [ ] `MissionPanel.jsx`: % area covered, sensors collected / total (from `sim/meta`), elapsed time, live DENM event log (last 20)
- [ ] Offline mode: use blank grid background if OpenStreetMap tiles are unavailable

### Acceptance Test
```bash
docker-compose -f docker-compose.sim.yml -f docker-compose.infra.yml up
# Open http://localhost:3000
# Observe: drones moving, grid filling in, sensors appearing on collection
# Connectivity lines appear/disappear as drones move
```

---

## M9 — Full Integration + Reproducibility

**Goal:** One command runs the entire simulation. Entity counts and map parameters are the single source of truth. Runs are reproducible.

### Tasks
- [x] `SIM_RANDOM_SEED` in `.env`; sensor `init.sh` uses it so the same seed always produces the same positions
- [x] `NUM_SENSORS`/`NUM_DRONES` in `.env` are the single source of truth; `deploy.replicas` reads them — `.env` is the only file to edit when scaling
- [ ] Add `Makefile` with convenience targets:
  - `make up` — `docker compose up`
  - `make down` — tear down all containers
  - `make logs` — tail all app logs
  - `make clean` — remove dangling volumes and images
- [x] All values parameterized via environment variables in `.env` / `.env-sample` with documented defaults
- [ ] Write `README.md` quickstart: install Docker, set replica counts, `make up`, open dashboard

### Acceptance Test
```bash
make up
# Full simulation runs, dashboard shows mission progress
# After mission completes: mockserver received all sensor data
# make down && make up  →  same sensor placement (same random_seed), reproducible run
```

---

## Dependency Graph

```
M1 (network baseline)
 └── M2 (proximity manager)
      ├── M3 (sensor entity)
      │    └── M4 (drone core)
      │         └── M5 (single drone E2E)
      │              └── M6 (multi-drone coordination)
      │                   └── M7 (base station + cloud)
      │                        └── M9 (integration)
      └── M8 (dashboard)  ← can start in parallel after M5
```

M8 can be developed in parallel with M6/M7 once M5 produces a live ETSI stream to observe.
