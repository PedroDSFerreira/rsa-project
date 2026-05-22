import asyncio
import dataclasses
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import mqtt_client
from state import state


class StartRequest(BaseModel):
    algorithm: Optional[str] = None

router = APIRouter()


def _serialise():
    return {
        "meta": state.meta,
        "entities": {sid: dataclasses.asdict(e) for sid, e in state.entities.items()},
        "links": state.links,
        "grid_map": state.grid_map,
        "grid_cells": state.grid_cells,
        "visit_counts": state.visit_counts,
        "deliveries": state.deliveries,
        "completed_drones": len(state.completed_drones),
        "tick": state.tick,
    }


@router.get("/state")
def get_state():
    return _serialise()


@router.get("/algorithms")
def get_algorithms():
    return state.algorithms


@router.post("/reset")
def post_reset():
    state.deliveries = {}
    state.grid_cells = {}
    state.visit_counts = {}
    state.grid_map = {}
    state.completed_drones = set()
    state.tick = 0
    return {"status": "reset"}


@router.post("/start")
def post_start(body: StartRequest = None):
    algorithm = body.algorithm if body else None
    if not algorithm:
        raise HTTPException(status_code=400, detail="algorithm is required")
    if state.algorithms and algorithm not in state.algorithms:
        raise HTTPException(status_code=400, detail=f"Unknown algorithm {algorithm!r}. Available: {state.algorithms}")
    mqtt_client.publish("sim/command/start", json.dumps({"algorithm": algorithm}))
    return {"status": "sent", "algorithm": algorithm}


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(_serialise())
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
