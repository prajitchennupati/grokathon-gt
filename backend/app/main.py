"""FastAPI app: REST controls + WebSocket state stream."""
from __future__ import annotations

import asyncio
import contextlib
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .bots import context as bot_context
from .bots.export import to_pdf
from .bots.service import watch_dropbox
from .config import settings
from .core import AppState, live_poll_loop, sim_loop
from .models import ROLES, BotPost

state = AppState()


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    tasks = [asyncio.create_task(sim_loop(state)), asyncio.create_task(watch_dropbox(state.bots)),
             asyncio.create_task(live_poll_loop(state))]
    if settings.source == "live":
        state.set_source("live")
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Clearance", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "llm_enabled": settings.llm_enabled, "offline": settings.offline, "demo_mode": settings.demo_mode}


@app.get("/api/scenario")
def scenario() -> dict[str, Any]:
    return state.engine.static_view()


class SourceBody(BaseModel):
    source: Literal["scenario", "live"]


@app.post("/api/source")
async def set_source(body: SourceBody) -> dict[str, Any]:
    """Switch between the scripted demo scenario and real ADS-B traffic."""
    state.set_source(body.source)
    await state.push()
    return {"source": state.source}


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
        await state.seek(body.value)
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
    except PermissionError as e:
        raise HTTPException(409, str(e))
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


# ---------------------------------------------------------------------------
# Bots
# ---------------------------------------------------------------------------


def _role(role: str) -> str:
    if role not in ROLES:
        raise HTTPException(404, f"unknown role {role}; expected one of {', '.join(ROLES)}")
    return role


def require_token(x_clearance_token: Optional[str] = Header(default=None)) -> None:
    """Runs before body validation, so unauthenticated callers never see schema errors."""
    if not x_clearance_token or not secrets.compare_digest(x_clearance_token, settings.token):
        raise HTTPException(401, "missing or invalid X-Clearance-Token")


@app.post("/api/bots/{role}/inbox", status_code=201, dependencies=[Depends(require_token)])
async def bot_inbox(role: str, post: BotPost) -> dict[str, Any]:
    """Grok Bots post finished work here. Proposed actions land in the approval queue."""
    if post.role != _role(role):
        raise HTTPException(422, f"body role {post.role!r} does not match URL role {role!r}")
    out = state.bots.ingest(post, via="webhook")
    await state.push()
    return {"ok": True, "output_id": out.id, "approvals_created": len(post.proposed_actions)}


@app.get("/api/bots/{role}/context", dependencies=[Depends(require_token)])
def bot_context_endpoint(role: str) -> dict[str, Any]:
    """What a live Grok Bot needs to do its job (sim picture, shift log, ...)."""
    return bot_context.for_role(state, _role(role))


class BotRun(BaseModel):
    fallback: bool = False  # true = skip the live Grok Bot and run the xAI fallback now


@app.post("/api/bots/{role}/run")
async def bot_run(role: str, body: BotRun = BotRun()) -> dict[str, Any]:
    _role(role)
    if body.fallback:
        state.bots.run_fallback_now(role)
    else:
        state.bots.trigger(role, "requested by controller")
    await state.push()
    return {"ok": True}


class BotMode(BaseModel):
    mode: Literal["live", "fallback"]


@app.post("/api/bots/{role}/mode")
async def bot_mode(role: str, body: BotMode) -> dict[str, Any]:
    state.bots.roster.bots[_role(role)].mode = body.mode
    state.log("bot", f"{role.title()} Bot switched to {'Grok Bot (live)' if body.mode == 'live' else 'Fallback (xAI API)'}",
              actor="controller")
    await state.push()
    return {"ok": True}


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "decline"]


@app.post("/api/approvals/{approval_id}")
async def approval_decision(approval_id: int, body: ApprovalDecision) -> dict[str, Any]:
    try:
        a = state.bots.decide(approval_id, body.decision)
    except KeyError as e:
        raise HTTPException(404, str(e))
    await state.push()
    return a.model_dump()


class Ack(BaseModel):
    item: int


@app.post("/api/bots/outputs/{output_id}/ack")
async def ack_item(output_id: int, body: Ack) -> dict[str, Any]:
    try:
        out = state.bots.ack(output_id, body.item)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    await state.push()
    return {"ok": True, "acked": out.acked}


@app.get("/api/bots/outputs/{output_id}/export.{fmt}")
def export_output(output_id: int, fmt: Literal["md", "pdf"]) -> Response:
    out = state.store.output(output_id)
    if out is None:
        raise HTTPException(404, "no such output")
    stamp = datetime.fromtimestamp(out.ts, timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    footer = f"Generated by Clearance ({out.role} helper) at {stamp}."
    name = re.sub(r"[^a-z0-9]+", "-", out.title.lower()).strip("-") or "report"
    if fmt == "md":
        body = f"{out.body_markdown}\n\n---\n_{footer}_\n"
        return Response(body, media_type="text/markdown",
                        headers={"Content-Disposition": f'attachment; filename="{name}.md"'})
    return Response(to_pdf(out.title, out.body_markdown, footer), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})


@app.get("/api/grokbot/{role}.md")
def grokbot_instructions(role: str) -> Response:
    """The paste-in instructions for a Grok Bot with this deployment's URLs filled in.
    The token stays a placeholder: share it with your teammate out of band."""
    from .config import REPO_DIR

    folder = REPO_DIR / "grokbot"
    text = (folder / f"{_role(role)}.md").read_text() + "\n" + (folder / "_common.md").read_text().split("-->", 1)[-1]
    text = text.replace("{{PUBLIC_BASE_URL}}", settings.public_base_url).replace("{{ROLE}}", role)
    return Response(text, media_type="text/markdown")


# ---------------------------------------------------------------------------
# Demo script
# ---------------------------------------------------------------------------


@app.get("/api/demo/steps")
def demo_steps() -> list[dict[str, Any]]:
    from .demo import STEPS

    return STEPS


@app.post("/api/demo/steps/{step_id}")
async def demo_step(step_id: str) -> dict[str, Any]:
    from .demo import run_step

    try:
        step = await run_step(state, step_id)
    except KeyError:
        raise HTTPException(404, f"no demo step {step_id}")
    await state.push()
    return step
