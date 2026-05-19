import asyncio
import dataclasses
import json
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import mqtt_client
from state import state

AVAILABLE_ALGORITHMS = ["boustrophedon", "greedy"]


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
        "deliveries": state.deliveries,
        "tick": state.tick,
    }


@router.get("/state")
def get_state():
    return _serialise()


@router.get("/algorithms")
def get_algorithms():
    return AVAILABLE_ALGORITHMS


@router.post("/start")
def post_start(body: StartRequest = None):
    algorithm = body.algorithm if body and body.algorithm in AVAILABLE_ALGORITHMS else AVAILABLE_ALGORITHMS[0]
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
