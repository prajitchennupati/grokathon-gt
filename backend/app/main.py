"""FastAPI app: REST controls + WebSocket state stream."""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings
from .core import AppState, sim_loop

state = AppState()


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(sim_loop(state))
    yield
    task.cancel()


app = FastAPI(title="Clearance", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "llm_enabled": settings.llm_enabled, "offline": settings.offline, "demo_mode": settings.demo_mode}


@app.get("/api/scenario")
def scenario() -> dict[str, Any]:
    return state.engine.static_view()


@app.get("/api/state")
def get_state() -> dict[str, Any]:
    return state.snapshot()


class SimControl(BaseModel):
    action: Literal["pause", "resume", "toggle", "restart", "speed", "seek", "auto_pause"]
    value: Optional[int] = None


@app.post("/api/sim/control")
async def sim_control(body: SimControl) -> dict[str, Any]:
    eng = state.engine
    if body.action == "pause":
        eng.running = False
    elif body.action == "resume":
        eng.running = True
    elif body.action == "toggle":
        eng.running = not eng.running
    elif body.action == "restart":
        state.restart()
    elif body.action == "speed":
        try:
            eng.set_speed(int(body.value or 1))
        except ValueError as e:
            raise HTTPException(400, str(e))
    elif body.action == "seek":
        if body.value is None:
            raise HTTPException(400, "seek needs value")
        state.seek(body.value)
    elif body.action == "auto_pause":
        state.auto_pause = bool(body.value)
    await state.push()
    return {"t": eng.t, "running": eng.running, "speed": eng.speed}


class AlertDecision(BaseModel):
    decision: Literal["approve", "dismiss"]


@app.post("/api/alerts/{alert_id}/decision")
async def alert_decision(alert_id: int, body: AlertDecision) -> dict[str, Any]:
    try:
        a = state.decide_alert(alert_id, body.decision)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    await state.push()
    return a.view()


class Instruction(BaseModel):
    callsign: str
    action: Literal["climb", "descend", "turn", "speed"]
    value: float


@app.post("/api/instructions")
async def instruction(body: Instruction) -> dict[str, Any]:
    """Controller-issued instruction from the scope (not an advisory)."""
    try:
        text = state.manual_instruction(body.callsign, body.action, body.value)
    except KeyError:
        raise HTTPException(404, f"{body.callsign} not on scope")
    await state.push()
    return {"phraseology": text}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    state.hub.clients.add(ws)
    try:
        await ws.send_json(state.snapshot())
        while True:
            await ws.receive_text()  # keepalive; controls go over REST
    except WebSocketDisconnect:
        pass
    finally:
        state.hub.clients.discard(ws)
