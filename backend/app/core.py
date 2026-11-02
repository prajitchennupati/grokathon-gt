"""Application state: sim engine, alerts, persistence and the WebSocket hub."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from fastapi import WebSocket

from .config import settings
from .bots.service import TRIGGERS, BotService
from .conflict.alerts import Alert, AlertManager
from .conflict.probe import Maneuver, validate_maneuver
from .live import feed
from .live.engine import LiveEngine, is_east_flow
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
        self.base_scenario = load_scenario(settings.scenarios_dir / settings.scenario)
        self.engine: SimEngine = SimEngine(self.base_scenario)
        self.source = "scenario"  # scenario | live
        self.store = store or Store(settings.db_path)
        self.alerts = AlertManager()
        self.hub = Hub()
        self.auto_pause = settings.demo_mode
        self.restrictions: list[str] = []
        self._tasks: set[asyncio.Task] = set()
        self._dirty = False
        self.bots = BotService(self)
        self.reset_counters()
        self.log("sim", f"Scenario loaded: {self.engine.scenario.name}")
        self._deferred = list(self.engine.fired)  # T+0 events run on the first tick, when the presenter hits run

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
        bots = self.bots.view()
        return {
            "type": "snapshot",
            "sim": self.engine.snapshot(),
            "alerts": [a.view() for a in self.alerts.alerts[-20:]],
            "log": [e.model_dump() for e in self.store.logs(limit=150)],
            "bots": bots,
            "restrictions": self.restrictions,
            "metrics": {
                **self.metrics,
                "bot_tasks_completed": sum(b["tasks_completed"] for b in bots["roster"]),
                "minutes_saved": sum(self.bots.minutes_saved.values()),
            },
            "source": self.source,
            "demo_mode": settings.demo_mode,
            "auto_pause": self.auto_pause,
            "llm": {"enabled": settings.llm_enabled, "offline": settings.offline, "model": settings.xai_model or None},
        }

    # ---- traffic source ----------------------------------------------------
    @property
    def live(self) -> bool:
        return isinstance(self.engine, LiveEngine)

    def set_source(self, source: str) -> None:
        if source == self.source:
            return
        for t in list(self._tasks):
            t.cancel()
        self.source = source
        self.engine = LiveEngine(self.base_scenario) if source == "live" else SimEngine(self.base_scenario)
        self.engine.running = source == "live"
        self.restart()
        if source == "live":
            self.engine.running = True
            self._deferred = []
            self._live_briefed = False
        self.log("sim", "Switched to LIVE traffic (adsb.lol / OpenSky)" if source == "live" else "Switched to demo scenario")

    # ---- sim lifecycle -----------------------------------------------------
    def restart(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        self.engine.reset()
        self.engine.running = self.live
        self.alerts.reset()
        self.store.new_run()
        self.bots.reset()
        self.restrictions = []
        self.reset_counters()
        self.log("sim", "Sim restarted")
        self._deferred = list(self.engine.fired)

    async def seek(self, t: int) -> None:
        """Jump to sim time t (restarting if needed). Advisories and Bot runs triggered on the
        way are awaited tick by tick, so a jump produces the same picture as running in real time."""
        if t < self.engine.t:
            self.restart()
        while self.engine.t < min(t, self.engine.scenario.duration_s):
            self.tick()
            if self._tasks:
                await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def tick(self) -> None:
        eng = self.engine
        deferred, self._deferred = self._deferred, []
        fired = eng.tick()
        for ev in deferred + fired:
            self.on_event(ev)
        new, escalated, resolved = self.alerts.update(eng.aircraft, eng.t, vfr=eng.alert_on_vfr,
                                                      resolve_after=eng.resolve_after_ticks,
                                                      vertical_ft=eng.vertical_alert_ft)
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
        if ev.kind in TRIGGERS:
            self.bots.trigger(TRIGGERS[ev.kind], ev.title.lower())
        if self.auto_pause and ev.kind in ("weather", "relief", "shift_end"):
            self.engine.running = False

    # ---- conflict advisories -------------------------------------------------
    async def generate_advisory(self, alert: Alert) -> None:
        if alert.status != "active":
            return
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
            if not self.live:  # live traffic is real: Clearance only records the decision
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
        if self.live:
            raise PermissionError("live traffic cannot be controlled")
        text = phraseology.instruction(callsign, action, value, ac.heading, ac.alt_ft, ac.gs_kt)
        self.engine.apply_action(callsign, action, value)
        self.log("instruction", text, actor="controller", callsign=callsign, action=action, value=value)
        return text


async def sim_loop(state: AppState) -> None:
    while True:
        eng = state.engine
        state.bots.check_live_timeouts()
        if eng.running and not eng.finished:
            started = time.monotonic()
            state.tick()
            await state.push()
            await asyncio.sleep(max(0.0, 1.0 / eng.speed - (time.monotonic() - started)))
        else:
            if state._dirty:
                await state.push()
            await asyncio.sleep(0.1)


LIVE_POLL_S = 5.0
METAR_REFRESH_S = 600.0


async def live_poll_loop(state: AppState) -> None:
    """Feeds the LiveEngine while live mode is on. Network failures keep the last picture."""
    import httpx

    last_wx = 0.0
    async with httpx.AsyncClient() as client:
        while True:
            eng = state.engine
            if isinstance(eng, LiveEngine):
                ap = eng.scenario.airport
                complete = eng.metar.get("metar") and eng.metar.get("taf")
                if time.time() - last_wx > (METAR_REFRESH_S if complete else 30):
                    wx = await feed.fetch_metar_taf(ap.icao, client)
                    last_wx = time.time()
                    if wx:
                        eng.metar = {**eng.metar, **wx}
                        if "wind_dir" in wx:
                            eng.east_flow = is_east_flow(wx.get("wind_dir"), wx.get("wind_kt"))
                try:
                    targets, provider = await feed.fetch(ap.lat, ap.lon, 45, client)
                    if state.engine is eng:
                        eng.update(targets, provider)
                        if not getattr(state, "_live_briefed", True):
                            state._live_briefed = True
                            state.bots.trigger("briefing", "shift start (live)")
                except Exception as e:
                    eng.error = str(e)[:200]
                    log.warning("live feed failed: %s", e)
                await state.push()
                await asyncio.sleep(LIVE_POLL_S)
            else:
                await asyncio.sleep(0.5)
