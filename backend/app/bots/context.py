"""Inputs each Bot role works from. The same context is served to live Grok Bots
(GET /api/bots/{role}/context) and to the fallback runners, so both produce the
same kind of output from the same facts."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from ..config import settings
from ..sim.geo import bearing

if TYPE_CHECKING:
    from ..core import AppState

ADJACENT_FACILITIES = [
    {"id": "ZTL", "name": "Atlanta Center (ZTL)", "handles": "arrivals over all four corner posts and the west gate"},
    {"id": "ATL", "name": "Atlanta Tower (ATL)", "handles": "final approach and departures"},
    {"id": "ATCSCC", "name": "Command Center (ATCSCC)", "handles": "national traffic management initiatives"},
]


@lru_cache(maxsize=1)
def _fixture() -> dict[str, Any]:
    return json.loads((settings.fixtures_dir / "briefing_inputs.json").read_text())


def briefing_inputs(state: "AppState") -> dict[str, Any]:
    """Sample fixture, with the real METAR/TAF and runway flow swapped in when live."""
    b = dict(_fixture())
    wx = getattr(state.engine, "metar", None)
    if wx and wx.get("metar"):
        east = getattr(state.engine, "east_flow", False)
        b.update(
            _note="METAR/TAF and runway flow are LIVE (aviationweather.gov). NOTAMs, closures, equipment and "
                  "TMIs are sample fixture data.",
            metar=wx["metar"], taf=wx.get("taf") or "", weather_outlook=[],
            # only real data in live mode: no sample NOTAMs, closures, equipment or TMIs
            notams=[], runway_closures=[], equipment=[], traffic_management=[],
            flow="East flow" if east else "West flow",
            active_runways={"arrivals": ["8L", "9R", "10"], "departures": ["8R", "9L"]} if east else b["active_runways"],
            sources=[s for s in b["sources"] if "aviationweather" in s["url"]],
        )
    return b


def _fmt_alt(ft: float) -> str:
    return f"{round(ft / 100):03d}"


def traffic(state: "AppState") -> list[dict[str, Any]]:
    out = []
    for ac in state.engine.aircraft.values():
        d = math.hypot(ac.x, ac.y)
        out.append({
            "callsign": ac.callsign, "type": ac.type, "rules": ac.flight_rules,
            "position": f"{round(d)} nm {_compass(bearing(0, 0, ac.x, ac.y))} of ATL",
            "altitude": _fmt_alt(ac.alt_ft), "assigned": _fmt_alt(ac.tgt_alt_ft),
            "heading": round(ac.heading), "gs_kt": round(ac.gs_kt),
            "next_fix": ac.next_fix, "runway": ac.land, "on_vector": ac.tgt_heading is not None,
            "destination": ac.destination,
        })
    return sorted(out, key=lambda r: r["callsign"])


def _compass(b: float) -> str:
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int(((b + 22.5) % 360) // 45)]


def weather_cells(state: "AppState") -> list[dict[str, Any]]:
    cells = []
    for c in state.engine.weather:
        cx = sum(p[0] for p in c.polygon_xy) / len(c.polygon_xy)
        cy = sum(p[1] for p in c.polygon_xy) / len(c.polygon_xy)
        affected = [ac.callsign for ac in state.engine.aircraft.values() if c.affects_fix and ac.next_fix == c.affects_fix]
        cells.append({
            "id": c.id, "title": c.title, "intensity": c.intensity,
            "center": f"{round(math.hypot(cx, cy))} nm {_compass(bearing(0, 0, cx, cy))} of ATL",
            "affects_fix": c.affects_fix, "moving": "ENE ~15 kt", "appeared": f"T+{c.appeared_t}s",
            "arrivals_routed_through_affected_fix": affected,
        })
    return cells


def alerts(state: "AppState") -> list[dict[str, Any]]:
    out = []
    for a in state.alerts.alerts:
        out.append({
            "id": a.id, "pair": [a.a, a.b], "status": a.status, "max_severity": a.max_severity,
            "detected": f"T+{a.created_t}s", "resolved": f"T+{a.resolved_t}s" if a.resolved_t is not None else None,
            "decision": a.decision, "suggestion": (a.advisory or {}).get("suggestion", {}).get("phraseology") if a.suggestion_valid else None,
            "closest_observed": a.min_sep, "timeline": a.timeline,
        })
    return out


def pending_approvals(state: "AppState") -> list[dict[str, Any]]:
    return [{"id": a.id, "role": a.role, **a.action} for a in state.store.approvals() if a.status == "pending"]


def shift_log(state: "AppState") -> list[dict[str, Any]]:
    return [{"t": f"T+{e.t_sim}s", "kind": e.kind, "actor": e.actor, "message": e.message} for e in state.store.logs()]


def for_role(state: "AppState", role: str) -> dict[str, Any]:
    eng = state.engine
    common = {
        "facility": eng.scenario.facility, "position": eng.scenario.position, "airport": eng.scenario.airport.icao,
        "sim_time": f"T+{eng.t}s", "advisory_only": "Prototype: every action is simulated and needs controller approval.",
    }
    if role == "briefing":
        return {**common, "inputs": briefing_inputs(state)}
    if role == "relief":
        b = briefing_inputs(state)
        return {
            **common,
            "traffic": traffic(state),
            "active_alerts": [a for a in alerts(state) if a["status"] == "active"],
            "pending_approvals": pending_approvals(state),
            "weather": {"metar": b["metar"], "cells": weather_cells(state)},
            "equipment": b["equipment"],
            "restrictions_in_effect": state.restrictions + b["traffic_management"],
            "active_runways": b["active_runways"],
            "recent_log": shift_log(state)[-25:],
        }
    if role == "coordination":
        return {
            **common,
            "weather_cells": weather_cells(state),
            "traffic": traffic(state),
            "adjacent_facilities": ADJACENT_FACILITIES,
            "restrictions_in_effect": state.restrictions,
        }
    if role == "paperwork":
        return {
            **common,
            "shift_log": shift_log(state),
            "alerts": alerts(state),
            "landed": eng.landed,
            "restrictions_in_effect": state.restrictions,
            "metrics": state.metrics,
        }
    raise KeyError(role)
