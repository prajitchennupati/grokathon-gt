"""Alert lifecycle on top of the per-tick probe, plus candidate resolutions."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from ..sim.kinematics import Aircraft
from .probe import Conflict, Maneuver, probe, validate_maneuver

RESOLVE_AFTER_TICKS = 3  # conflict must be absent this long before the alert clears
SEVERITY_RANK = {"predicted": 1, "imminent": 2}


@dataclass
class Alert:
    id: int
    key: str
    a: str
    b: str
    created_t: int
    severity: str
    max_severity: str
    geometry: dict[str, Any]
    status: str = "active"  # active | resolved
    resolved_t: Optional[int] = None
    advisory_state: str = "pending"  # pending | ready
    advisory: Optional[dict[str, Any]] = None
    advisory_source: str = ""
    advisory_error: str = ""
    suggestion_valid: bool = False
    validation_note: str = ""
    decision: Optional[str] = None  # approved | dismissed
    decision_t: Optional[int] = None
    min_sep: Optional[dict[str, Any]] = None  # observed (actual), not predicted
    timeline: list[dict[str, Any]] = field(default_factory=list)
    _missing: int = 0

    @property
    def pair(self) -> tuple[str, str]:
        return self.a, self.b

    def view(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class AlertManager:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.alerts: list[Alert] = []
        self._next_id = 1

    def active(self) -> list[Alert]:
        return [a for a in self.alerts if a.status == "active"]

    def get(self, alert_id: int) -> Optional[Alert]:
        return next((a for a in self.alerts if a.id == alert_id), None)

    def update(self, aircraft: dict[str, Aircraft], t: int, vfr: bool = True,
               resolve_after: int = RESOLVE_AFTER_TICKS, vertical_ft: float = 1000.0) -> tuple[list[Alert], list[Alert], list[Alert]]:
        """Run the probe and advance alert state. Returns (new, escalated, resolved)."""
        conflicts = {c.key: c for c in probe(aircraft.values(), vfr=vfr, vertical_ft=vertical_ft)}
        new, escalated, resolved = [], [], []
        by_key = {a.key: a for a in self.active()}

        for key, c in conflicts.items():
            alert = by_key.get(key)
            if alert is None:
                alert = Alert(id=self._next_id, key=key, a=c.a, b=c.b, created_t=t, severity=c.severity,
                              max_severity=c.severity, geometry=c.as_dict())
                alert.timeline.append({"t": t, "event": f"{c.severity} conflict detected", **c.as_dict()})
                self._next_id += 1
                self.alerts.append(alert)
                new.append(alert)
            else:
                alert._missing = 0
                if SEVERITY_RANK[c.severity] > SEVERITY_RANK[alert.severity]:
                    alert.timeline.append({"t": t, "event": f"escalated to {c.severity}", **c.as_dict()})
                    escalated.append(alert)
                if SEVERITY_RANK[c.severity] > SEVERITY_RANK[alert.max_severity]:
                    alert.max_severity = c.severity
                alert.severity = c.severity
                alert.geometry = c.as_dict()

        for alert in self.active():
            a, b = aircraft.get(alert.a), aircraft.get(alert.b)
            if a is not None and b is not None:
                lat = math.hypot(a.x - b.x, a.y - b.y)
                if alert.min_sep is None or lat < alert.min_sep["lateral_nm"]:
                    alert.min_sep = {"t": t, "lateral_nm": round(lat, 2), "vertical_ft": round(abs(a.alt_ft - b.alt_ft)),
                                     "alt_a": round(a.alt_ft), "alt_b": round(b.alt_ft)}
            if alert.key in conflicts:
                continue
            alert._missing += 1
            if alert._missing >= resolve_after or a is None or b is None:
                alert.status, alert.resolved_t = "resolved", t
                alert.timeline.append({"t": t, "event": "conflict resolved"})
                resolved.append(alert)
        return new, escalated, resolved


# ---------------------------------------------------------------------------
# Candidate resolutions: deterministic, each one verified by the probe
# ---------------------------------------------------------------------------

MIN_ALT_FT = 3000
MAX_ALT_FT = 17000


def _candidates_for(ac: Aircraft) -> Iterable[tuple[int, Maneuver]]:
    """(cost, maneuver). Lower cost = smaller disruption."""
    base_alt = int(round(ac.tgt_alt_ft / 1000.0) * 1000)
    for cost, dalt in ((1, -1000), (1, 1000), (3, -2000), (3, 2000)):
        alt = base_alt + dalt
        if MIN_ALT_FT <= alt <= MAX_ALT_FT:
            yield cost, Maneuver(ac.callsign, "descend" if dalt < 0 else "climb", alt)
    for cost, dh in ((2, 20), (2, -20), (3, 30), (3, -30), (4, 45), (4, -45)):
        yield cost, Maneuver(ac.callsign, "turn", round((ac.heading + dh) / 5.0) * 5 % 360 or 360)
    yield 5, Maneuver(ac.callsign, "speed", max(180, round((ac.gs_kt - 40) / 10.0) * 10))


def validated_candidates(aircraft: dict[str, Aircraft], alert_key: str, limit: int = 6) -> list[Maneuver]:
    a, b = alert_key.split("|")
    ranked: list[tuple[int, int, Maneuver]] = []
    for order, cs in enumerate((a, b)):
        if cs in aircraft:
            ranked += [(cost, order, m) for cost, m in _candidates_for(aircraft[cs])]
    ranked.sort(key=lambda r: (r[0], r[1]))
    out = []
    for _, _, m in ranked:
        ok, _ = validate_maneuver(aircraft.values(), alert_key, m)
        if ok:
            out.append(m)
            if len(out) >= limit:
                break
    return out


def conflict_from_alert(alert: Alert) -> Conflict:
    g = alert.geometry
    return Conflict(a=g["a"], b=g["b"], t_cpa=g["t_cpa"], lateral_nm=g["lateral_nm"], vertical_ft=g["vertical_ft"],
                    t_los=g["t_los"], severity=g["severity"])
