"""Application state: sim engine, alerts, persistence and the WebSocket hub."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from fastapi import WebSocket

from .config import settings
from .conflict.alerts import Alert, AlertManager
from .conflict.probe import Maneuver, validate_maneuver
from .llm import advisory, phraseology
from .sim.engine import FiredEvent, SimEngine
from .sim.scenario import load_scenario
from .store import Store

log = logging.getLogger("clearance")


class Hub:
    """Fan-out of state snapshots to connected WebSocket clients."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def broadcast(self, msg: dict[str, Any]) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


class AppState:
    def __init__(self, store: Optional[Store] = None) -> None:
        self.engine = SimEngine(load_scenario(settings.scenarios_dir / settings.scenario))
        self.store = store or Store(settings.db_path)
        self.alerts = AlertManager()
        self.hub = Hub()
        self.auto_pause = settings.demo_mode
        self._tasks: set[asyncio.Task] = set()
        self._dirty = False
        self.reset_counters()
        self.log("sim", f"Scenario loaded: {self.engine.scenario.name}")

    # ---- helpers -----------------------------------------------------------
    def reset_counters(self) -> None:
        self.metrics = {"alerts_raised": 0, "suggestions_approved": 0, "suggestions_dismissed": 0}

    def log(self, kind: str, message: str, actor: str = "system", **data: Any) -> None:
        self.store.log(self.engine.t, kind, message, actor, **data)
        self._dirty = True

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def push(self) -> None:
        self._dirty = False
        await self.hub.broadcast(self.snapshot())

    def snapshot(self) -> dict[str, Any]:
        return {
            "type": "snapshot",
            "sim": self.engine.snapshot(),
            "alerts": [a.view() for a in self.alerts.alerts[-20:]],
            "log": [e.model_dump() for e in self.store.logs(limit=150)],
            "metrics": self.metrics,
            "demo_mode": settings.demo_mode,
            "auto_pause": self.auto_pause,
            "llm": {"enabled": settings.llm_enabled, "offline": settings.offline, "model": settings.xai_model or None},
        }

    # ---- sim lifecycle -----------------------------------------------------
    def restart(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        self.engine.reset()
        self.engine.running = False
        self.alerts.reset()
        self.store.new_run()
        self.reset_counters()
        self.log("sim", "Sim restarted")

    def seek(self, t: int) -> None:
        """Jump to sim time t (restarting if needed). Conflicts found on the way are raised normally."""
        if t < self.engine.t:
            self.restart()
        while self.engine.t < min(t, self.engine.scenario.duration_s):
            self.tick()

    def tick(self) -> None:
        eng = self.engine
        fired = eng.tick()
        for ev in fired:
            self.on_event(ev)
        new, escalated, resolved = self.alerts.update(eng.aircraft, eng.t)
        for a in new:
            self.metrics["alerts_raised"] += 1
            self.log("alert", f"{a.severity.upper()} conflict {a.a} / {a.b}: {a.geometry['lateral_nm']} nm, "
                     f"{a.geometry['vertical_ft']} ft in {a.geometry['t_cpa']} s", alert_id=a.id, **a.geometry)
            self.spawn(self.generate_advisory(a))
            if self.auto_pause:
                eng.running = False
        for a in escalated:
            self.log("alert", f"Conflict {a.a} / {a.b} now IMMINENT (CPA {a.geometry['t_cpa']} s)", alert_id=a.id)
        for a in resolved:
            self.log("alert", f"Conflict {a.a} / {a.b} resolved", alert_id=a.id, min_sep=a.min_sep)
        self.revalidate()
        if eng.finished:
            eng.running = False

    def on_event(self, ev: FiredEvent) -> None:
        self.log("event", f"{ev.title}: {ev.detail}".rstrip(": "), event=ev.kind, **ev.data)
        if self.auto_pause and ev.kind in ("weather", "relief", "shift_end"):
            self.engine.running = False

    # ---- conflict advisories -------------------------------------------------
    async def generate_advisory(self, alert: Alert) -> None:
        try:
            result, ok, note = await advisory.advise(alert, self.engine.aircraft, self.engine.scenario.name)
        except Exception as e:  # never let an advisory failure break the sim
            log.exception("advisory failed")
            alert.advisory_state, alert.advisory_error = "ready", str(e)
            alert.validation_note = "advisory unavailable"
            await self.push()
            return
        alert.advisory = result.value.model_dump()
        alert.advisory_source = result.source
        alert.advisory_error = result.error
        alert.suggestion_valid = ok
        alert.validation_note = note
        alert.advisory_state = "ready"
        s = result.value.suggestion
        self.log("advisory", f"Advisory for {alert.a}/{alert.b} ({result.source}, {result.latency_ms} ms): "
                 + (s.phraseology if ok else f"no validated suggestion ({note})"), alert_id=alert.id)
        await self.push()

    def revalidate(self) -> None:
        """Pending suggestions are re-checked every tick against the live picture."""
        for a in self.alerts.active():
            if a.advisory_state != "ready" or a.decision or not a.advisory or not a.advisory["suggestion"]["phraseology"]:
                continue
            s = a.advisory["suggestion"]
            ok, note = validate_maneuver(self.engine.aircraft.values(), a.key, Maneuver(s["callsign"], s["action"], s["value"]))
            a.suggestion_valid, a.validation_note = ok, note

    def decide_alert(self, alert_id: int, decision: str) -> Alert:
        a = self.alerts.get(alert_id)
        if a is None:
            raise KeyError("no such alert")
        if a.decision:
            raise ValueError(f"already {a.decision}")
        if decision == "approve":
            if not (a.advisory and a.suggestion_valid):
                raise ValueError("no validated suggestion to approve")
            s = a.advisory["suggestion"]
            ac = self.engine.aircraft.get(s["callsign"])
            if ac is None:
                raise ValueError(f"{s['callsign']} no longer on scope")
            self.engine.apply_action(s["callsign"], s["action"], float(s["value"]))
            a.decision, a.decision_t = "approved", self.engine.t
            a.timeline.append({"t": self.engine.t, "event": f"controller approved: {s['phraseology']}"})
            self.metrics["suggestions_approved"] += 1
            self.log("approval", f"APPROVED {s['phraseology']}", actor="controller", alert_id=a.id, **s)
        elif decision == "dismiss":
            a.decision, a.decision_t = "dismissed", self.engine.t
            a.timeline.append({"t": self.engine.t, "event": "controller dismissed suggestion"})
            self.metrics["suggestions_dismissed"] += 1
            self.log("approval", f"DISMISSED advisory for {a.a}/{a.b}", actor="controller", alert_id=a.id)
        else:
            raise ValueError(decision)
        return a

    def manual_instruction(self, callsign: str, action: str, value: float) -> str:
        ac = self.engine.aircraft.get(callsign)
        if ac is None:
            raise KeyError(callsign)
        text = phraseology.instruction(callsign, action, value, ac.heading, ac.alt_ft, ac.gs_kt)
        self.engine.apply_action(callsign, action, value)
        self.log("instruction", text, actor="controller", callsign=callsign, action=action, value=value)
        return text


async def sim_loop(state: AppState) -> None:
    while True:
        eng = state.engine
        if eng.running and not eng.finished:
            started = time.monotonic()
            state.tick()
            await state.push()
            await asyncio.sleep(max(0.0, 1.0 / eng.speed - (time.monotonic() - started)))
        else:
            if state._dirty:
                await state.push()
            await asyncio.sleep(0.1)
