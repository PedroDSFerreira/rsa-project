import asyncio
import dataclasses

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import mqtt_client
from state import state

router = APIRouter()


def _serialise():
    return {
        "meta": state.meta,
        "entities": {sid: dataclasses.asdict(e) for sid, e in state.entities.items()},
        "links": state.links,
        "grid_map": state.grid_map,
        "grid_cells": state.grid_cells,
        "deliveries": list(state.deliveries),
        "tick": state.tick,
    }


@router.get("/state")
def get_state():
    return _serialise()


@router.post("/start")
def post_start():
    mqtt_client.publish("sim/command/start", "{}")
    return {"status": "sent"}


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(_serialise())
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
