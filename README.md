# RSA Project - Autonomous Forest Data Collection

This repository simulates an autonomous drone fleet that sweeps a forest grid,
detects static sensors, collects environmental readings, and delivers them to a
base station. Coordination uses MQTT for control/data and V2X-style CAM/DENM
messages for local awareness.

## Architecture overview

Services (Docker Compose):

- mqtt-central: Mosquitto broker for control and data.
- base_station: Starts missions, assigns start rows, aggregates deliveries.
- drone: Replica set that performs coverage, peer coordination, and collection.
- sensor: Replica set that serves readings on request.
- proximity-manager: Computes range links and optionally applies MAC filtering.
- dashboard-backend: FastAPI state aggregation and API.
- dashboard-frontend: Web UI.

Message flow summary:

- sim/announce/{id}: Entity discovery (drones, sensors, base station).
- sim/command/start -> sim/start: Mission start and algorithm selection.
- vanetza/in/* and vanetza/out/*: CAM (presence) and DENM (cell state) exchange.
- sim/links: Proximity-based links published each tick.
- sensor/{id}/request and sensor/{id}/response/{drone_id}: Data collection.
- sim/base/data_delivery and sim/delivery/{sensor_id}: Delivery reporting.

## Setup

Prerequisites:

- Docker and Docker Compose (v2).

Optional: initialize a local environment file if you want to customize defaults:

```bash
make prepare-env
```

Common environment variables (can be set in .env or exported):

- NUM_DRONES, NUM_SENSORS
- SIM_AREA_SW_LAT, SIM_AREA_SW_LNG
- SIM_AREA_WIDTH_M, SIM_AREA_HEIGHT_M
- CELL_SIZE_M
- DRONE_RANGE_M, BASE_RANGE_M
- TICK_REAL_MS, DRONE_SPEED_M_S, DRONE_COLLECTION_TIME_S

## Run the simulation

Build and start all services:

```bash
make build
make up
```

Or, run in detached mode:

```bash
make upd
```

Open the dashboard:

http://localhost:3000

From the UI, select an algorithm and start the mission. You can also trigger a
start via the backend API:

```bash
curl -X POST http://localhost:8000/start \
	-H 'Content-Type: application/json' \
	-d '{"algorithm":"frontier"}'
```

Stop and clean up:

```bash
make down
```

## How coverage works (high level)

- The base station publishes sim/start with map bounds and per-drone start rows.
- Each drone builds a coverage grid and selects waypoints via the chosen
	algorithm.
- Drones publish CAM messages each tick and DENM updates for CLAIMED, VISITED,
	and SENSOR_FOUND cells.
- Proximity-manager computes which peers are in range and publishes sim/links.
- Drones request sensor data on proximity and deliver all collected readings to
	the base station at the end of the mission.

## Add a new coverage algorithm

1) Create a new module in apps/drone/algorithms (for example, spiral.py).

2) Subclass Algorithm and register it:

```python
from algorithms.base import Algorithm, register

@register("spiral")
class SpiralTraversal(Algorithm):
		def setup(self, grid, start, all_starts):
				# Initialize your internal plan here.
				pass

		def next_waypoint(self, grid, position):
				# Return the next Position or None when done.
				pass
```

3) The algorithms package auto-imports all modules, so no extra wiring is
	 needed. Rebuild and restart the stack so drones publish the new algorithm
	 name to sim/algorithms.

4) Select the new algorithm in the dashboard and start a mission.

## Project layout

- apps/base_station: mission control and delivery aggregation.
- apps/drone: drone agent, navigation, comms, and algorithms.
- apps/sensor: sensor identity and data responses.
- infra/proximity_manager: range simulation and MAC filtering.
- infra/dashboard: backend and frontend visualization.