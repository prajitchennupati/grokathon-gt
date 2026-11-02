"""FastAPI app: REST controls + WebSocket state stream."""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings
from .sim.engine import SimEngine
from .sim.scenario import load_scenario


class Hub:
    """Fan-out of state snapshots to connected WebSocket clients."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def broadcast(self, msg: dict[str, Any]) -> None:
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


class AppState:
    def __init__(self) -> None:
        self.engine = SimEngine(load_scenario(settings.scenarios_dir / settings.scenario))
        self.hub = Hub()

    def snapshot(self) -> dict[str, Any]:
        return {"type": "snapshot", "sim": self.engine.snapshot(), "demo_mode": settings.demo_mode}

    async def push(self) -> None:
        await self.hub.broadcast(self.snapshot())


state = AppState()


async def sim_loop() -> None:
    while True:
        eng = state.engine
        if eng.running and not eng.finished:
            eng.tick()
            await state.push()
            await asyncio.sleep(1.0 / eng.speed)
        else:
            await asyncio.sleep(0.1)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(sim_loop())
    yield
    task.cancel()


app = FastAPI(title="Clearance", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "llm_enabled": settings.llm_enabled, "offline": settings.offline}


@app.get("/api/scenario")
def scenario() -> dict[str, Any]:
    return state.engine.static_view()


@app.get("/api/state")
def get_state() -> dict[str, Any]:
    return state.snapshot()


class SimControl(BaseModel):
    action: str  # pause | resume | toggle | restart | speed | seek
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
        eng.reset()
        eng.running = False
    elif body.action == "speed":
        try:
            eng.set_speed(int(body.value or 1))
        except ValueError as e:
            raise HTTPException(400, str(e))
    elif body.action == "seek":
        if body.value is None:
            raise HTTPException(400, "seek needs value")
        if body.value < eng.t:
            eng.reset()
        eng.run_until(body.value)
    else:
        raise HTTPException(400, f"unknown action {body.action}")
    await state.push()
    return {"t": eng.t, "running": eng.running, "speed": eng.speed}


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
