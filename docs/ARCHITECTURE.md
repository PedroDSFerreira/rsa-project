# Architecture — Sistema Autónomo de Recolha de Dados em Ambiente Florestal

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Component Architecture](#2-component-architecture)
3. [Communication Architecture — Vanetza-NAP](#3-communication-architecture--vanetza-nap)
4. [Drone Coverage Algorithm](#4-drone-coverage-algorithm)
5. [ProximityManager (Simulation Engine)](#5-proximitymanager-simulation-engine)
6. [Data Flow](#6-data-flow)
7. [Real-Time Dashboard](#7-real-time-dashboard)
8. [Project Structure](#8-project-structure)
9. [Open Problems & Design Decisions](#9-open-problems--design-decisions)

---

## 1. System Overview

The simulation runs entirely inside Docker. Every entity — base station, drones, and sensors — is a set of containers on a shared Docker network (`vanetzalan0`). ETSI C-ITS messages (CAM, DENM) are exchanged as real IEEE 802.11p/ITS-G5 Ethernet frames over this virtual network, using **Vanetza-NAP** as the protocol stack.

A dedicated **ProximityManager** container drives the simulation physics: it enforces proximity constraints by dynamically blocking/unblocking MAC addresses between containers based on each drone's reported position. Sensor and drone apps operate fully autonomously — no central controller knows or manipulates mission state. No custom kernel or hardware is required.

```
                    ┌──────────────────────────────────────────────────────┐
                    │                  vanetzalan0 (192.168.98.0/24)        │
                    │                                                        │
  ┌─────────────┐  │  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
  │  Proximity  │  │  │ vanetza  │  │ vanetza  │  │ vanetza  │            │
  │  Manager    │  │  │ drone-1  │  │ drone-2  │  │ sensor-1 │  ...       │
  │  (Docker    │  │  │  + app   │  │  + app   │  │  + app   │            │
  │   SDK only) │  │  └──────────┘  └──────────┘  └──────────┘            │
  └──────┬──────┘  │                                                        │
         │         │  ┌─────────────────┐                                  │
         │         │  │  vanetza-base   │                                  │
         │         │  │  + app-base     │                                  │
         │         │  └─────────────────┘                                  │
         │         └──────────────────────────────────────────────────────┘
         │
         │  docker exec block/unblock
         │  reads drone CAMs from mqtt-central
         │  publishes sim/links, sim/meta
         ▼
  ┌─────────────────┐◄───── All vanetza containers (remote MQTT fwd)
  │  mqtt-central   │◄───── sim/links, sim/meta (ProximityManager)
  │  (Mosquitto)    │
  └────────┬────────┘
           ├──────────────► Dashboard Backend (parallel consumer)
           └──────────────► ProximityManager (drone CAMs only)
```

---

## 2. Component Architecture

Each entity runs as a **single bundled container** that extends `ghcr.io/nap-it/vanetza-nap:latest`. An `entrypoint.sh` init script runs before the main processes: it queries the Docker API to discover the container's own replica index, derives a unique identity from that index, then starts vanetza-nap as a background process and the Python app as the foreground process.

### Identity Assignment at Startup

Docker Compose names replica containers deterministically as `<project>-<service>-<N>`. The init script reads the container's own name via the Docker socket to extract index N, then computes:

| Field | Sensor (type byte `01`) | Drone (type byte `02`) |
|---|---|---|
| `VANETZA_STATION_ID` | `20 + N` | `10 + N` |
| `VANETZA_MAC_ADDRESS` | `6e:06:e0:03:01:<N>` | `6e:06:e0:03:02:<N>` |
| Start position | Random within map bounds (seeded by N) | Base station lat/lng |

After vanetza-nap starts, the app publishes a retained `sim/announce/{station_id}` message to `mqtt-central` with `{station_id, mac, container_name, ip, lat, lng, entity_type}`. This is the discovery handshake — MQTT retention ensures late subscribers receive all announces automatically.

### 2.1 Sensor

**Service:** `sensor` (replicas: N from `simulation_config.yaml`)

Each sensor container extends vanetza-nap, adds Python, and runs both processes:

```
entrypoint.sh
  ├── vanetza-nap (background) — STATION_TYPE=10, hardcoded GPS, CAM every 2s
  └── main.py     (foreground) — publishes sim/announce, serves sensor/request_data
```

When a drone enters radio range (MAC unblocked by ProximityManager), the drone receives the sensor's CAM and connects directly to the sensor's MQTT broker using the IP from the earlier `sim/announce`. No central authority is involved in the data exchange.

### 2.2 Drone

**Service:** `drone` (replicas: N from `simulation_config.yaml`)

Each drone container extends vanetza-nap, adds Python, and runs both processes:

```
entrypoint.sh
  ├── vanetza-nap (background) — STATION_TYPE=5, GPS published by app
  └── main.py     (foreground) — publishes sim/announce, runs DroneAgent
```

```
┌──────────────────────────────────────────────────────┐
│  drone-N container                                    │
│                                                        │
│  ┌──────────────────────────────────────────────┐    │
│  │  DroneAgent (Python)                          │    │
│  │  - simulated position (lat, lng, heading)     │    │
│  │  - coverage grid (cell states)               │    │
│  │  - sensor registry (ip, lat/lng per sensor)  │    │
│  │  - state machine (EXPLORING / COLLECTING /   │    │
│  │                    RETURNING / AT_BASE)       │    │
│  └──────────────────┬───────────────────────────┘    │
│                     │  MQTT (127.0.0.1:1883)          │
│  ┌──────────────────┼────────────────────────────┐   │
│  │  vanetza-nap     ▼                             │   │
│  │  vanetza/in/cam  ──► encode ──► vanetzalan0    │   │
│  │  vanetza/in/denm ──► encode ──► vanetzalan0    │   │
│  │  vanetzalan0 ──► decode ──► vanetza/out/cam    │   │
│  │  vanetzalan0 ──► decode ──► vanetza/out/denm   │   │
│  └────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

### 2.3 Base Station

**Containers:** `vanetza-base` + `app-base`

Same sidecar pattern as the drone. The app process:
- Receives CAMs from drones in its radio range (proximity managed by ProximityManager)
- Receives returning drones' data delivery directly via MQTT (`sim/base/data_delivery`) when a drone transitions to `AT_BASE`
- Tracks mission completion state
- Pushes collected data to the cloud endpoint (HTTP POST to a configurable URL)

Key configuration:
```
VANETZA_STATION_TYPE=15               # RSU
VANETZA_STATION_ID=1
VANETZA_USE_HARDCODED_GPS=true
VANETZA_LATITUDE=<fixed base position>
VANETZA_LONGITUDE=<fixed base position>
VANETZA_CAM_PERIODICITY=1000
START_EMBEDDED_MOSQUITTO=true
SUPPORT_MAC_BLOCKING=true
VANETZA_REMOTE_MQTT_BROKER=mqtt-central
VANETZA_REMOTE_MQTT_PORT=1883
```

### 2.4 ProximityManager

**Container:** `proximity-manager` (Python)

A thin **infrastructure-only** service. It has no knowledge of mission state, sensor data, or drone decisions. Its sole responsibility is to simulate the physics of radio range by enforcing MAC-level connectivity. Responsibilities:
- Parses `simulation_config.yaml` for map geometry, entity count, and radio range thresholds
- **Discovery phase**: subscribes to `sim/announce` on `mqtt-central`; waits until all expected entities (`num_drones + num_sensors + 1 base`) have announced
- Once all entities are announced: blocks all pairs (fully isolated), then starts the simulation tick loop
- Subscribes to `mqtt-central` `+/vanetza/own/cam` to track live entity positions
- Computes pairwise distances (drone↔drone, drone↔sensor, drone↔base) at every tick
- Issues `block`/`unblock` commands via Docker SDK `exec` to enforce proximity
- Publishes `sim/links` (connectivity matrix) to `mqtt-central` each tick
- Publishes `sim/meta` once after discovery (map bounds, num_drones, num_sensors) for the dashboard

### 2.5 Dashboard

**Containers:** `dashboard-backend` (FastAPI) + `dashboard-frontend` (Nginx + React)

See §7 for full details.

---

## 3. Communication Architecture — Vanetza-NAP

### 3.1 Entity MQTT Interface Pattern

Every vanetza container embeds a Mosquitto broker. The co-located app process connects to it on `localhost:1883`. All vanetza containers also forward decoded received messages to `mqtt-central` via `VANETZA_REMOTE_MQTT_BROKER`, enabling the ProximityManager and dashboard to independently observe the network from one place.

```
App process                Vanetza-NAP             ITS-G5 (Docker network)
─────────────────────────────────────────────────────────────────────────
publish vanetza/in/cam ──► encode UPER + GeoNet ──► broadcast on vanetzalan0
publish vanetza/in/denm ─► encode UPER + GeoNet ──► broadcast on vanetzalan0
subscribe vanetza/out/cam ◄── decode + JSON ◄──── received frame on vanetzalan0
subscribe vanetza/out/denm ◄─ decode + JSON ◄──── received frame on vanetzalan0
```

### 3.2 MQTT Topic Map

| Direction | Topic | Publisher | Subscriber | Content |
|---|---|---|---|---|
| App → Vanetza | `vanetza/in/cam` | drone-app, base-app | vanetza | Drone position update |
| App → Vanetza | `vanetza/in/denm` | drone-app | vanetza | Coverage events |
| Vanetza → App | `vanetza/out/cam` | vanetza | drone-app, base-app | Incoming CAMs from other nodes |
| Vanetza → App | `vanetza/out/denm` | vanetza | drone-app | Incoming DENMs |
| Vanetza → Central | `obu{id}/vanetza/out/cam` | vanetza (remote fwd) | ProximityManager, dashboard | CAMs received by station `id` from others |
| Vanetza → Central | `obu{id}/vanetza/own/cam` | vanetza (remote fwd) | ProximityManager, dashboard | Self-generated CAMs from station `id` |
| Vanetza → Central | `obu{id}/vanetza/out/denm` | vanetza (remote fwd) | dashboard | DENMs received by station `id` |
| Entity App → Central | `sim/announce/{station_id}` | every entity app (on startup) | ProximityManager, dashboard | `{station_id, mac, container_name, ip, lat, lng, entity_type}` — discovery handshake; published with `retain=True` so late subscribers receive all entities |
| Drone App → Central | `sim/grid_sync/{station_id}` | drone-app | drone-app (target peer) | Full local grid JSON — one message published when a new peer first comes into C-ITS range |
| Drone App → Sensor | `sensor/request_data` | drone-app | sensor-app | Request to collect sensor data (connects to sensor IP:1883 directly) |
| Sensor App → Drone | `sensor/data_response` | sensor-app | drone-app | Synthetic environmental data payload |
| ProximityManager → Central | `sim/links` | proximity-manager | dashboard | Current connectivity matrix (each tick) |
| ProximityManager → Central | `sim/meta` | proximity-manager | dashboard | Map bounds, entity count (once after discovery) |

### 3.3 CAM — Situational Awareness

The drone application publishes a CAM to `vanetza/in/cam` at each simulation tick, encoding its current simulated position, heading, and speed. Other nodes receive it on `vanetza/out/cam`. The base station uses CAMs to reconstruct the mission map.

Minimal CAM published by drone app:
```json
{
  "camParameters": {
    "basicContainer": {
      "stationType": 5,
      "referencePosition": {
        "latitude": 40.6310,
        "longitude": -8.6580,
        "positionConfidenceEllipse": {"semiMajorAxisLength": 50, "semiMinorAxisLength": 50, "semiMajorAxisOrientation": 0},
        "altitude": {"altitudeValue": 0, "altitudeConfidence": 15}
      }
    },
    "highFrequencyContainer": {
      "basicVehicleContainerHighFrequency": {
        "heading": {"headingValue": 45.0, "headingConfidence": 1},
        "speed":   {"speedValue": 5.0,   "speedConfidence": 1},
        "driveDirection": 0,
        "vehicleLength": {"vehicleLengthValue": 1.5, "vehicleLengthConfidenceIndication": 0},
        "vehicleWidth": 1.5,
        "longitudinalAcceleration": {"value": 0.0, "confidence": 0},
        "curvature": {"curvatureValue": 0, "curvatureConfidence": 7},
        "curvatureCalculationMode": 0,
        "yawRate": {"yawRateValue": 0.0, "yawRateConfidence": 8}
      }
    }
  }
}
```

Drones identify sensors (stationType=10) by filtering incoming CAMs on `fields.cam.camParameters.basicContainer.stationType`. When a sensor CAM is received, it means the drone is in radio range of that sensor and can collect its data.

### 3.4 DENM — Coverage Event Coordination

DENMs are used for broadcast coverage events that all in-range drones must hear. The `situation.eventType.ccAndScc` field encodes the event type using **ETSI cause code 97 (dangerousSituation)** repurposed for simulation. The `management.eventPosition` encodes the relevant geographic point (cell center or sensor position). The `management.actionId.sequenceNumber` carries the **cell index** (`row × grid_cols + col`), letting peers resolve the exact cell without re-running the GPS→grid conversion.

| subCauseCode | Meaning | `eventPosition` | `sequenceNumber` |
|---|---|---|---|
| `0` | Cell **claimed** — drone is en route | Center of claimed cell | Cell index |
| `1` | Cell **visited** — no sensor found | Center of visited cell | Cell index |
| `2` | Sensor **collected** — data gathered | Sensor's GPS position | Cell index |

Grid synchronisation between two drones is **not** done via DENM. When a drone first comes into C-ITS range of a peer, it publishes its full local grid as a single JSON payload to `sim/grid_sync/{peer_station_id}` on `mqtt-central`. This avoids flooding the C-ITS channel with one DENM per cell (up to 400 messages per sync).

DENM sent by drone on sensor collection:
```json
{
  "management": {
    "actionId": {"originatingStationId": 2, "sequenceNumber": 12},
    "detectionTime": 1762875837.0,
    "referenceTime": 1762875837.0,
    "eventPosition": {
      "latitude":  40.6342,
      "longitude": -8.6601,
      "positionConfidenceEllipse": {"semiMajorConfidence": 1, "semiMinorConfidence": 1, "semiMajorOrientation": 0},
      "altitude": {"altitudeValue": 0, "altitudeConfidence": 1}
    },
    "validityDuration": 600,
    "stationType": 5
  },
  "situation": {
    "informationQuality": 7,
    "eventType": {
      "ccAndScc": { "dangerousSituation97": 2 }
    }
  }
}
```

> **Note on ETSI conformance:** `dangerousSituation` (97) with subcauses 0–2 falls within the `reserved` subcause range for that code, which vanetza-nap accepts. This is a deliberate repurposing for simulation purposes and is documented here to avoid ambiguity.

### 3.5 Out-of-Range Simulation via MAC Blocking

The ProximityManager controls connectivity by calling `block`/`unblock` inside target containers via the Docker SDK. This filters frames at L2 (ebtables), making the disconnect transparent to vanetza and the app layer.

```
┌─────────────────────────────────────────────────────┐
│  ProximityManager tick (every 200 ms real time)      │
│                                                       │
│  for each pair (A, B):                               │
│    dist = haversine(pos_A, pos_B)                    │
│    if dist ≤ RADIO_RANGE_M:                          │
│      if not already connected(A, B):                 │
│        docker exec A  unblock <MAC_B>               │
│        docker exec B  unblock <MAC_A>               │
│    else:                                             │
│      if currently connected(A, B):                  │
│        docker exec A  block   <MAC_B>               │
│        docker exec B  block   <MAC_A>               │
└─────────────────────────────────────────────────────┘
```

The ProximityManager maintains a connectivity state matrix to avoid redundant exec calls. The base station has a **larger effective range** (simulating the cellular uplink zone) configured separately from the drone-to-drone radio range. Static entities (sensors, base station) have their positions loaded from `simulation_config.yaml` at startup — only drone positions are tracked live from the CAM feed.

---

## 4. Drone Coverage Algorithm

### 4.1 Map Representation

The simulation area is a 2D rectangle defined in `simulation_config.yaml` (e.g., 1000 m × 1000 m). It is discretized into a grid of square cells (e.g., 50 m × 50 m = 400 cells for a 1 km² area). Cells are addressed by `(row, col)` or equivalently by their center GPS coordinates.

Each drone maintains a local copy of the grid. Each cell has one of four states:

| State | Meaning |
|---|---|
| `UNKNOWN` | Not yet reached or heard about |
| `CLAIMED` | Another drone is en route (received a claim DENM) |
| `VISITED` | Searched, no sensor present |
| `SENSOR_FOUND` | Sensor was found and collected here |

### 4.2 Primary Algorithm: Grid-Based Dynamic Coverage

At each decision step, a drone in `EXPLORING` state selects its next target cell using a **greedy nearest-unclaimed frontier** strategy:

1. Build a candidate set: all cells in state `UNKNOWN`.
2. Score each candidate: `score(c) = -distance(drone_pos, cell_center(c))` (closest = highest score). Add a small bonus for cells **adjacent to already-visited cells** to encourage contiguous coverage and reduce backtracking.
3. Select the highest-scoring cell as `target`.
4. Mark it locally as `CLAIMED`.
5. Broadcast a DENM (subCauseCode=0) with `eventPosition` = cell center so other drones stop considering it.

When the drone arrives at the cell:
- If no sensor CAM received: mark cell `VISITED`, broadcast DENM (subCauseCode=1).
- If sensor CAM received: enter `COLLECTING`, gather data, broadcast DENM (subCauseCode=2), mark cell `SENSOR_FOUND`.

#### Handling Stale Claims

A claim DENM has a limited `validityDuration`. If a drone that claimed a cell goes out of range (e.g., returns to base or fails), its claimed cells age out and revert to `UNKNOWN` after the validity window. Other drones will then re-claim them on their next decision cycle.

### 4.3 Initial Strip Pre-assignment (Boustrophedon)

To reduce initial contention, the base station pre-assigns **horizontal strips** of the map to drones at mission launch. Each drone receives its strip boundaries via a direct MQTT message from the base station app (`sim/drone/<id>/mission`).

Within its assigned strip, the drone sweeps in a **boustrophedon (lawnmower) pattern**:

```
Drone 1 strip          Drone 2 strip         Drone 3 strip
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│→→→→→→→→→→→→▼│      │→→→→→→→→→→→→▼│      │→→→→→→→→→→→→▼│
│▼←←←←←←←←←←←│      │▼←←←←←←←←←←←│      │▼←←←←←←←←←←←│
│→→→→→→→→→→→→▼│      │→→→→→→→→→→→→▼│      │→→→→→→→→→→→→▼│
│▼←←←←←←←←←←←│      │   ...        │      │   ...        │
│   ...        │      └──────────────┘      └──────────────┘
└──────────────┘
```

The strip assignment converts the complex multi-agent coordination problem into N independent single-agent lawnmower problems for the initial sweep.

### 4.4 Dynamic Rebalancing

After a drone finishes its assigned strip (all cells in its strip are `VISITED` or `SENSOR_FOUND`), it transitions to the global dynamic coverage mode (§4.2) and helps complete any `UNKNOWN` cells remaining in other drones' strips. This handles:
- One drone being faster than others
- Drone returning to base early (battery/storage full) leaving its strip incomplete

### 4.5 Drone State Machine

```
          ┌─────────────┐
  launch  │             │  strip complete / no UNKNOWN cells nearby
─────────►│  EXPLORING  │◄──────────────────────────────────────────┐
          │             │                                            │
          └──────┬──────┘                                           │
                 │ sensor CAM received                              │
                 ▼                                                  │
          ┌─────────────┐  data collected / DENM sent               │
          │ COLLECTING  │────────────────────────────────────────── ┘
          └──────┬──────┘
                 │ storage full OR mission_complete flag from base
                 ▼
          ┌─────────────┐
          │  RETURNING  │  navigate toward base station position
          └──────┬──────┘
                 │ in range of base (orchestrator unblocks base MAC)
                 ▼
          ┌─────────────┐
          │   AT_BASE   │  offload data, await new mission or idle
          └─────────────┘
```

### 4.6 DTN-Style Grid Synchronization (Store-Carry-Forward)

A drone that was out of range of others when sensor events occurred carries that knowledge in its local grid. When it later enters range of another drone, it performs a **grid sync**: it publishes its full local grid as a single JSON payload to `sim/grid_sync/{peer_station_id}` on `mqtt-central`. The peer subscribes to `sim/grid_sync/{own_station_id}` and merges the received state into its own grid (taking the highest-known state per cell). This is a lightweight implementation of a **Delay-Tolerant Networking (DTN) carry-and-forward** mechanism.

The sync is triggered when a drone receives a CAM from a peer whose `stationID` it has not seen before.

---

## 5. ProximityManager (Simulation Engine)

### 5.1 Startup & Container Provisioning

The simulation is driven by a single configuration file:

```yaml
# simulation_config.yaml
map:
  width_m: 1000
  height_m: 1000
  origin_lat: 40.630
  origin_lng: -8.660
  cell_size_m: 50

entities:
  num_drones: 3
  num_sensors: 10

radio:
  drone_range_m: 150       # drone-to-drone and drone-to-sensor range
  base_range_m: 300        # base station uplink range

simulation:
  tick_real_ms: 200        # wall-clock ms per simulation tick
  tick_sim_s: 1.0          # simulated seconds per tick
  drone_speed_m_s: 5.0     # simulated drone speed

base_station:
  lat: 40.630
  lng: -8.660
```

The `docker-compose.yml` declares `sensor` and `drone` as services with `deploy.replicas` matching the entity counts in this config. No compose file is ever generated. Each container self-assigns its unique identity at startup (see §2).

```
# Set replica counts in docker-compose.yml to match simulation_config.yaml, then:
docker compose up
```

To reproduce an exact run, set `random_seed` in the config — sensors will pick the same random positions.

### 5.2 Simulation Loop

The ProximityManager runs a fixed-rate loop:

```python
# pseudo-code
while simulation_running:
    tick_start = time.monotonic()

    # 1. Read latest drone positions from central MQTT cache
    #    Sensor and base station positions are static, loaded from config at startup
    drone_positions = mqtt_cache.get_all_cam_positions(stationType=5)

    # 2. Evaluate all pairwise distances, update connectivity matrix
    for A, B in all_pairs(entities):
        dist = haversine(pos[A], pos[B])
        threshold = BASE_RANGE if is_base(A) or is_base(B) else DRONE_RANGE
        update_connectivity(A, B, dist <= threshold)

    # 3. Publish connectivity snapshot to mqtt-central for dashboard
    mqtt.publish("sim/links", json.dumps(build_links_snapshot()))

    elapsed = time.monotonic() - tick_start
    time.sleep(max(0, TICK_REAL_MS/1000 - elapsed))
```

### 5.3 Connectivity Management

The ProximityManager maintains a `connectivity_matrix[A][B] = bool` and only calls `block`/`unblock` when the state changes, minimizing Docker exec overhead:

```python
def update_connectivity(A, B, should_connect):
    was_connected = connectivity_matrix[A][B]
    if should_connect and not was_connected:
        docker_exec(A, f"unblock {mac[B]}")
        docker_exec(B, f"unblock {mac[A]}")
        connectivity_matrix[A][B] = True
    elif not should_connect and was_connected:
        docker_exec(A, f"block {mac[B]}")
        docker_exec(B, f"block {mac[A]}")
        connectivity_matrix[A][B] = False
```

All containers start with all MACs blocked (fully isolated). The orchestrator then selectively opens connectivity based on proximity.

---

## 6. Data Flow

```
Sensor app (random position, all MACs blocked by default)
  │
  │  ProximityManager detects drone within DRONE_RANGE_M
  │  → docker exec sensor-N unblock <drone_mac>
  │  → docker exec drone-N  unblock <sensor_mac>
  │
  ├─► sensor vanetza broadcasts CAM (stationType=10, lat/lng) → drone vanetza
  │
  ▼
Drone app receives CAM on vanetza/out/cam where stationType=10
  → identifies sensor by stationId, looks up IP from sim/announce registry
  → connects to sensor's local MQTT broker ({sensor_ip}:1883)
  → publishes to sensor/request_data
  → sensor app receives request, replies with payload on sensor/data_response
  → drone app receives and stores {sensor_id, data_payload}
  → enters COLLECTING state
  → publishes DENM (subCauseCode=2, eventPosition=sensor GPS) to vanetza/in/denm
  → vanetza broadcasts DENM on vanetzalan0
  → other in-range drones receive DENM → mark cell SENSOR_FOUND → avoid this area
  → dashboard receives DENM on mqtt-central → reveals sensor marker on map
  → drone marks cell SENSOR_FOUND locally → transitions back to EXPLORING
  │
  │  ... drone continues exploring, returns to base when storage full ...
  │
  ▼
Drone enters base station range
  → ProximityManager unblocks base ↔ drone
  → Drone receives CAM from stationType=15 → enters AT_BASE state
  → Drone app connects to base station broker (base-station:1883)
  → Publishes collected data to sim/base/data_delivery
  → Base station app aggregates all sensor datasets
  │
  ▼
Base station app
  → HTTP POST to cloud endpoint (configurable URL in config)
  → Dashboard observes mission state from ETSI stream (all drones idle at base)
```

---

## 7. Real-Time Dashboard

### 7.1 Stack

| Component | Technology | Purpose |
|---|---|---|
| `mqtt-central` | Mosquitto 2 | Central message bus; all vanetza containers forward to it |
| `dashboard-backend` | Python FastAPI + paho-mqtt | Subscribes to MQTT, maintains live state, serves WebSocket |
| `dashboard-frontend` | React + Leaflet.js | Real-time map visualization via WebSocket |
| Metrics (optional) | Grafana + Prometheus | System-level metrics from vanetza Prometheus endpoints |

### 7.2 Backend

The FastAPI backend subscribes to `mqtt-central` on startup as a **pure observer** — it derives all world state from the ETSI message stream with no dependency on any mission controller:
- `vanetza/out/cam` → updates drone/sensor/base position cache; sensors only appear here after discovery (MAC unblocked by ProximityManager)
- `vanetza/out/denm` → updates coverage grid cell states (claimed/visited/sensor_found)
- `sim/links` → updates connectivity overlay (published by ProximityManager each tick)
- `sim/meta` → receives map bounds and entity count at startup (retained message from ProximityManager)

It maintains a single **`SimState`** object representing the current simulation:
```python
@dataclass
class SimState:
    drones: dict[int, DroneState]     # stationId → position, heading, state
    sensors: dict[int, SensorState]   # stationId → position, collected, collected_by
    base: BaseState                    # position, mission_status
    grid: list[list[CellState]]        # 2D array of cell states
    tick: int
    timestamp: float
```

Any change to `SimState` is pushed to all connected WebSocket clients as a JSON diff or full snapshot (configurable). Clients connect to `ws://dashboard-backend:8000/ws`.

### 7.3 Frontend

The React + Leaflet frontend renders:

- **Map layer:** OpenStreetMap tiles (or a custom blank grid if offline)
- **Coverage grid overlay:** semi-transparent colored cells
  - `UNKNOWN` → transparent
  - `CLAIMED` → pale blue
  - `VISITED` → light green
  - `SENSOR_FOUND` → dark orange
- **Drone markers:** animated icons showing heading arrow; clicking shows CAM details
- **Sensor markers:** hidden until discovered (the dashboard only reveals sensors when their `collected=true` — simulating the unknown-position constraint)
- **Base station marker:** fixed; shows data received count
- **Mission progress panel:** % area covered, sensors collected / total, elapsed sim time
- **Live log:** last 20 DENM events

WebSocket updates are applied incrementally to avoid full re-renders. React state is managed with `useReducer` and a `SimStateContext`.

### 7.4 Grafana (Optional Metrics)

Each vanetza container exposes Prometheus metrics at `VANETZA_PROMETHEUS_PORT=9100`:
```
observed_packets_count_total{direction="tx", message="cam"}
observed_packets_count_total{direction="rx", message="denm"}
observed_packets_latency_total{...}
```

A Grafana container can scrape all vanetza endpoints and display:
- CAM/DENM tx/rx rates per entity
- Encoding/decoding latency histograms
- Network message totals over time

---

## 8. Project Structure

```
project/
├── simulation_config.yaml           # Primary simulation parameters
├── scripts/
│   └── generate_sim.py             # Generates docker-compose.sim.yml from config
├── docker-compose.sim.yml           # Auto-generated (not edited manually)
├── docker-compose.infra.yml         # Static infra: mqtt-central, proximity-manager, dashboard
│
├── proximity_manager/
│   ├── Dockerfile
│   ├── main.py                      # Simulation loop (proximity only)
│   ├── proximity.py                 # Distance calc + block/unblock logic
│   └── requirements.txt
│
├── apps/
│   ├── drone/
│   │   ├── Dockerfile
│   │   ├── main.py                  # DroneAgent: state machine + coverage algorithm
│   │   ├── coverage_grid.py         # Grid representation + cell selection
│   │   ├── vanetza_client.py        # MQTT wrapper for vanetza/in|out topics
│   │   └── requirements.txt
│   ├── sensor/
│   │   ├── Dockerfile
│   │   ├── main.py                  # Generates synthetic data, serves sensor/request_data
│   │   └── requirements.txt
│   └── base_station/
│       ├── Dockerfile
│       ├── main.py                  # Mission launch + cloud upload
│       └── requirements.txt
│
├── dashboard/
│   ├── backend/
│   │   ├── Dockerfile
│   │   ├── main.py                  # FastAPI + WebSocket + MQTT subscriber
│   │   └── requirements.txt
│   └── frontend/
│       ├── Dockerfile               # Nginx
│       ├── src/
│       │   ├── App.jsx
│       │   ├── MapView.jsx          # Leaflet map + overlays
│       │   ├── MissionPanel.jsx
│       │   └── SimContext.jsx       # WebSocket state management
│       └── package.json
│
└── docs/
    └── ARCHITECTURE.md              # This file
```

---

## 9. Open Problems & Design Decisions

### 9.1 Grid Sync Payload Size

Grid sync is performed over MQTT (`sim/grid_sync/{id}`), not over the C-ITS channel. A full 400-cell grid serialised as JSON is roughly 10–20 KB — well within MQTT message limits. No throttling or fragmentation is needed, and exactly one sync message fires per new peer contact.

### 9.2 Stale Claim Recovery

If a drone claims a cell but never sends a VISITED DENM (due to going out of range before arriving), that cell stays `CLAIMED` until the DENM `validityDuration` expires. Setting `validityDuration` too low causes thrashing; too high causes long dead zones. A reasonable default is `cell_width_m / drone_speed_m_s × 2` seconds.

### 9.3 Sensor Station Type Collision

Using `stationType=10` for sensors is a repurposing of the ETSI "specialVehicle" type. This is unambiguous within our closed simulation but should be documented clearly if the codebase is extended. All filtering on `stationType` should use named constants (`STATION_TYPE_SENSOR = 10`).

### 9.4 Drone Position Authority

The drone app is the sole authority on its own simulated position (it publishes it via CAM). The ProximityManager trusts these reported positions for proximity calculations. This means a buggy drone app could report inconsistent positions. For robustness, the ProximityManager could optionally dead-reckon positions independently from the last known heading/speed and alert on large divergences.

### 9.5 Cloud Upload

The base station's cloud upload is an HTTP POST to a configurable endpoint. For the simulation demo, this can point to a local mock server (`mockserver` container) that logs received payloads. Replacing the URL with a real cloud endpoint (e.g., AWS S3, Azure Blob, or a custom REST API) requires no code change.

### 9.6 Time Acceleration

The simulation runs with a configurable time multiplier (`tick_sim_s / tick_real_ms`). At the default of 200 ms real ↔ 1 s simulated, a 1 km² mission with 3 drones at 5 m/s takes roughly 5–10 minutes of wall-clock time. Increasing `tick_sim_s` (or decreasing `tick_real_ms`) speeds up the simulation at the cost of coarser proximity granularity.

### 9.7 Scalability of MAC Blocking

The Docker `exec block` approach has latency proportional to container startup overhead (typically 10–50 ms per call). With N drones and M sensors, the worst-case number of pair-state changes per tick is O(N+M)². For 3 drones + 10 sensors = 13 entities → 78 pairs. This is well within the 200 ms tick budget. If scaling to larger fleets, replace Docker exec calls with a pre-installed `nc` listener inside each container that accepts block/unblock commands via TCP.
