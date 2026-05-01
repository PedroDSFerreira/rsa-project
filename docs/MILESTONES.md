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
- [ ] Create `proximity_manager/` with `Dockerfile`, `requirements.txt` (`paho-mqtt`, `docker`)
- [ ] Implement `proximity.py`: connectivity matrix, `block(container, mac)` / `unblock(container, mac)` via Docker SDK
- [ ] Implement `main.py`: read `simulation_config.yaml`, subscribe to `mqtt-central` `vanetza/out/cam` for drone positions, compute haversine distances each tick, call `proximity.py`
- [ ] Publish `sim/meta` (retained) to `mqtt-central` on startup: `{ "map": {...}, "num_drones": N, "num_sensors": M }`
- [ ] Publish `sim/links` each tick: `{ "connected": [[id_a, id_b], ...], "tick": N }`
- [ ] Start all containers with all MACs fully blocked (isolated by default)
- [ ] Add ProximityManager to `docker-compose.dev.yml` with Docker socket mounted

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

**Goal:** A sensor container self-generates synthetic data and serves it to any requester via direct MQTT. The sensor announces itself via CAM.

### Tasks
- [ ] Create `apps/sensor/` with `Dockerfile`, `requirements.txt`
- [ ] Implement `main.py`:
  - Read `SENSOR_ID`, `SENSOR_LAT`, `SENSOR_LNG` from environment
  - Generate synthetic data payload at startup: `{ "temperature": ..., "humidity": ..., "co2": ..., "timestamp": ... }`
  - Subscribe to `sensor/request_data` on local broker (port 1883)
  - Reply with payload on `sensor/data_response` when a request arrives
- [ ] Add a sensor service to `docker-compose.dev.yml` alongside its vanetza sidecar (`VANETZA_STATION_TYPE=10`, `VANETZA_CAM_PERIODICITY=2000`, `VANETZA_USE_HARDCODED_GPS=true`)
- [ ] Expose sensor broker port to the Docker network so other containers can connect by service name

### Acceptance Test
```bash
# Manually request data from the sensor container
docker exec any-container mosquitto_pub \
  -h sensor-1 -p 1883 \
  -t "sensor/request_data" -m '{"requester_id": 99}'

docker exec any-container mosquitto_sub \
  -h sensor-1 -p 1883 \
  -t "sensor/data_response" -C 1

# Expected: JSON payload with temperature, humidity, co2
```

---

## M4 — Drone Core: Position Publishing + State Machine

**Goal:** A drone app publishes its simulated position as CAMs and runs a minimal state machine. No coverage logic yet — just movement and ETSI communication.

### Tasks
- [ ] Create `apps/drone/` with `Dockerfile`, `requirements.txt`
- [ ] Implement `vanetza_client.py`: thin wrapper to publish/subscribe CAM and DENM on the local vanetza broker
- [ ] Implement `main.py` with `DroneAgent`:
  - Read `DRONE_ID`, `DRONE_START_LAT`, `DRONE_START_LNG`, `DRONE_SPEED` from environment
  - State machine with stubs: `IDLE → EXPLORING → COLLECTING → RETURNING → AT_BASE`
  - At each tick: advance simulated position toward current waypoint, publish CAM with updated lat/lng/heading/speed
  - Subscribe to `vanetza/out/cam`: log incoming CAMs with `stationType`
  - Subscribe to `vanetza/out/denm`: log incoming DENMs
- [ ] Add a drone service to `docker-compose.dev.yml`

### Acceptance Test
```bash
# Subscribe to mqtt-central, watch drone CAMs flowing in
mosquitto_sub -h localhost -p 1884 -t "vanetza/out/cam" -v

# Expected: periodic CAMs from the drone with updating lat/lng
# ProximityManager should pick up the position and adjust connectivity
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
  - On `EXPLORING`: call `next_target`, set waypoint, publish DENM subCauseCode=0 (claim)
  - On arrival at cell: publish DENM subCauseCode=1 (visited), mark `VISITED`
  - On receiving CAM with `stationType=10`: transition to `COLLECTING`
    - Connect to `sensor-{stationId}:1883`, publish `sensor/request_data`, await `sensor/data_response`
    - Store payload, publish DENM subCauseCode=2 (sensor collected), mark `SENSOR_FOUND`
  - On `RETURNING`: navigate to base station GPS position
  - On receiving CAM with `stationType=15` while `RETURNING`: transition to `AT_BASE`
    - Connect to `base-station:1883`, publish collected data to `sim/base/data_delivery`
- [ ] Implement base station app stub (`apps/base_station/main.py`): subscribe `sim/base/data_delivery`, log received payloads
- [ ] Create `scripts/generate_sim.py`: read `simulation_config.yaml`, write `docker-compose.sim.yml` with all services

### Acceptance Test
```bash
python scripts/generate_sim.py simulation_config.yaml
docker-compose -f docker-compose.sim.yml up

# Observe logs:
# - Drone publishes CAMs with changing position
# - Drone publishes DENM claim/visited for each cell
# - When drone reaches sensor range → data collected
# - Drone returns to base → base station logs received payload
```

---

## M6 — Multi-Drone: DENM Coordination + Grid Sync

**Goal:** Multiple drones share the area without duplicate work. DENMs from other drones update each drone's local grid. DTN grid sync fires when two drones first come into range.

### Tasks
- [ ] Base station app (`apps/base_station/main.py`):
  - At mission start, compute equal horizontal strip for each drone based on `simulation_config.yaml`
  - Publish strip assignment to each drone via `sim/drone/{id}/mission` on `mqtt-central`
- [ ] Drone app: subscribe `sim/drone/{id}/mission` on startup, wait for strip assignment before starting `EXPLORING`
- [ ] Drone app: on receiving DENM from another drone:
  - subCauseCode=0 → mark cell at `eventPosition` as `CLAIMED`
  - subCauseCode=1 → mark cell as `VISITED`
  - subCauseCode=2 → mark cell as `SENSOR_FOUND`
  - subCauseCode=3 → bulk update grid (grid sync)
- [ ] Drone app: implement DTN grid sync trigger
  - Track set of known peer `stationAddr` values from received CAMs
  - On first CAM from a previously-unseen peer: burst DENMs subCauseCode=3 for all non-`UNKNOWN` cells (throttled: 1 per 50 ms, `SENSOR_FOUND` cells first)
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

## M9 — Full Integration + Simulation Generator

**Goal:** One command configures and runs the entire simulation from `simulation_config.yaml`. System is reproducible and clean.

### Tasks
- [ ] Finalize `scripts/generate_sim.py`:
  - Randomly place sensors within map bounds (seeded by optional `random_seed` in config)
  - Assign unique station IDs, MAC addresses, static IPs
  - Write `docker-compose.sim.yml` (never hand-edited)
  - Write `sim_run_manifest.json` alongside it (records exact sensor positions for post-run analysis)
- [ ] Add `Makefile` (or `justfile`) with convenience targets:
  - `make generate` — run `generate_sim.py`
  - `make up` — `docker-compose ... up`
  - `make down` — tear down all containers
  - `make logs` — tail all app logs
  - `make clean` — remove generated files
- [ ] Parameterize all hardcoded values via environment variables with documented defaults
- [ ] Write `README.md` quickstart: install Docker, run `make generate && make up`, open dashboard

### Acceptance Test
```bash
make generate && make up
# Full simulation runs, dashboard shows mission progress
# After mission completes: mockserver received all sensor data
# make down && make generate && make up  →  new random sensor placement, same result
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
