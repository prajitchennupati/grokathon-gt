"""Conflict advisories: Grok explains the conflict and picks a resolution; the
deterministic probe has the final say on whether the suggestion is shown."""
from __future__ import annotations

import json
import math
from typing import Any

from ..conflict.alerts import Alert, validated_candidates
from ..conflict.probe import Maneuver, validate_maneuver
from ..models import ConflictAdvisory, Suggestion
from ..sim.geo import bearing
from ..sim.kinematics import Aircraft
from . import phraseology
from .client import LLMResult, structured

SYSTEM = """You are Clearance, an advisory copilot for an FAA TRACON arrival controller.
You never issue instructions yourself: the controller approves or dismisses everything.
Given a predicted loss of separation (3 nm lateral / 1,000 ft vertical minima), write:
- summary: one or two plain-English sentences a busy controller can read in 3 seconds
  (who, where, when, how close).
- suggestion: ONE instruction to ONE of the two aircraft. Strongly prefer an option from
  `validated_candidates` (each has already been checked by a deterministic conflict probe);
  copy its callsign/action/value exactly. action is climb|descend|turn|speed; value is the
  new altitude in feet, the new magnetic heading in degrees, or the new speed in knots.
  phraseology must be standard FAA phraseology (JO 7110.65), e.g.
  "Delta fourteen twenty-three, climb and maintain one zero thousand."
- rationale: one sentence on why this option over the others (traffic, route, workload).
Respond with JSON only."""


def _ac_brief(ac: Aircraft) -> dict[str, Any]:
    return {
        "callsign": ac.callsign, "type": ac.type, "altitude_ft": round(ac.alt_ft), "assigned_altitude_ft": round(ac.tgt_alt_ft),
        "heading": round(ac.heading), "groundspeed_kt": round(ac.gs_kt), "vertical_speed_fpm": round(ac.vs_fpm),
        "next_fix": ac.next_fix, "landing_runway": ac.land, "on_vector": ac.tgt_heading is not None,
    }


def _nearby(aircraft: dict[str, Aircraft], alert: Alert, radius_nm: float = 15.0) -> list[dict[str, Any]]:
    a = aircraft[alert.a]
    out = []
    for ac in aircraft.values():
        if ac.callsign in alert.pair:
            continue
        d = math.hypot(ac.x - a.x, ac.y - a.y)
        if d <= radius_nm:
            out.append({"callsign": ac.callsign, "range_nm_from_" + a.callsign: round(d, 1),
                        "bearing_from_" + a.callsign: round(bearing(a.x, a.y, ac.x, ac.y)),
                        "altitude_ft": round(ac.alt_ft), "heading": round(ac.heading)})
    return out


def describe(m: Maneuver, ac: Aircraft) -> dict[str, Any]:
    return {"callsign": m.callsign, "action": m.action, "value": m.value,
            "phraseology": phraseology.instruction(m.callsign, m.action, m.value, ac.heading, ac.alt_ft, ac.gs_kt)}


def canned(alert: Alert, aircraft: dict[str, Aircraft], candidates: list[Maneuver]) -> ConflictAdvisory:
    g = alert.geometry
    a, b = aircraft[alert.a], aircraft[alert.b]
    vfr = next((ac.callsign for ac in (a, b) if ac.flight_rules == "VFR"), None)
    summary = (f"{alert.a} and {alert.b}{f' (VFR, {vfr})' if vfr else ''} converging at "
               f"{round(a.alt_ft / 100):03d}/{round(b.alt_ft / 100):03d}; "
               f"predicted {g['lateral_nm']:.1f} nm and {g['vertical_ft']:.0f} ft apart in {g['t_cpa']} s.")
    if candidates:
        m = candidates[0]
        ac = aircraft[m.callsign]
        verb = {"climb": "climbing", "descend": "descending", "turn": "turning", "speed": "slowing"}[m.action]
        return ConflictAdvisory(
            summary=summary,
            suggestion=Suggestion(**describe(m, ac)),
            rationale=f"Smallest verified change: {verb} {m.callsign} clears the conflict with no new conflicts inside 120 s.",
        )
    return ConflictAdvisory(
        summary=summary,
        suggestion=Suggestion(callsign=alert.a, action="climb", value=a.tgt_alt_ft, phraseology=""),
        rationale="No single maneuver restores 3 nm / 1,000 ft before CPA; consider a safety alert and traffic advisory.",
    )


async def advise(alert: Alert, aircraft: dict[str, Aircraft], scenario_name: str) -> tuple[LLMResult[ConflictAdvisory], bool, str]:
    """Returns (result, suggestion_valid, validation_note)."""
    candidates = validated_candidates(aircraft, alert.key)
    payload = {
        "conflict": alert.geometry,
        "aircraft": [_ac_brief(aircraft[alert.a]), _ac_brief(aircraft[alert.b])],
        "nearby_traffic": _nearby(aircraft, alert),
        "validated_candidates": [describe(m, aircraft[m.callsign]) for m in candidates],
    }
    fallback = canned(alert, aircraft, candidates)  # built now: aircraft may land while we await
    result = await structured(
        task="conflict_advisory",
        cache_key=f"{scenario_name}:{alert.key}:t{alert.created_t}",
        system=SYSTEM,
        user=json.dumps(payload, indent=1),
        schema=ConflictAdvisory,
        canned=lambda: fallback,
    )
    s = result.value.suggestion
    if not s.phraseology:
        return result, False, "no candidate maneuver resolves this conflict"
    ok, note = validate_maneuver(aircraft.values(), alert.key, Maneuver(s.callsign, s.action, s.value))
    return result, ok, note
