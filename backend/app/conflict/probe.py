"""Deterministic conflict probe.

Each aircraft is projected straight ahead for LOOKAHEAD_S seconds at its current
heading and groundspeed (altitude moves toward its assigned altitude at the
standard rate and levels off). A pair is in conflict when, at any second inside
the window, lateral separation < 3 nm AND vertical separation < 1,000 ft.

Severity follows the time of closest point of approach within the conflict:
  imminent  -> CPA in < 60 s
  predicted -> CPA in 60-120 s

Pairs where both aircraft are established on final to *different* runways are
suppressed (simultaneous parallel approaches), mirroring a conflict-alert
suppression area at a real facility.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Optional

from ..sim.kinematics import CLIMB_FPM, DESCENT_FPM, SPEED_RATE_KTS, TURN_RATE_DPS, Aircraft
from ..sim.geo import heading_diff, velocity

LOOKAHEAD_S = 120
LATERAL_NM = 3.0
VERTICAL_FT = 1000.0
IMMINENT_S = 60


@dataclass
class Maneuver:
    """A single instruction applied at t=0 of the projection."""

    callsign: str
    action: str  # climb | descend | turn | speed
    value: float


@dataclass
class Conflict:
    a: str
    b: str
    t_cpa: int  # seconds from now
    lateral_nm: float  # at CPA
    vertical_ft: float  # at CPA
    t_los: int  # seconds until first loss of separation
    severity: str

    @property
    def key(self) -> str:
        return "|".join(sorted((self.a, self.b)))

    def as_dict(self) -> dict:
        return {
            "a": self.a,
            "b": self.b,
            "t_cpa": self.t_cpa,
            "lateral_nm": round(self.lateral_nm, 2),
            "vertical_ft": round(self.vertical_ft),
            "t_los": self.t_los,
            "severity": self.severity,
        }


def cpa(p1: tuple[float, float], v1: tuple[float, float], p2: tuple[float, float], v2: tuple[float, float],
        horizon: float = LOOKAHEAD_S) -> tuple[float, float]:
    """Analytic straight-line CPA. Returns (t_cpa seconds clamped to [0, horizon], distance nm)."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    dvx, dvy = v2[0] - v1[0], v2[1] - v1[1]
    vv = dvx * dvx + dvy * dvy
    t = 0.0 if vv < 1e-12 else max(0.0, min(horizon, -(dx * dvx + dy * dvy) / vv))
    return t, math.hypot(dx + dvx * t, dy + dvy * t)


def project(ac: Aircraft, horizon: int = LOOKAHEAD_S, maneuver: Optional[Maneuver] = None) -> list[tuple[float, float, float]]:
    """(x, y, alt) for t = 0..horizon. Straight line unless a maneuver is applied."""
    x, y, alt, hdg, gs = ac.x, ac.y, ac.alt_ft, ac.heading, ac.gs_kt
    tgt_alt, tgt_hdg, tgt_gs = ac.tgt_alt_ft, None, gs
    if maneuver is not None:
        if maneuver.action in ("climb", "descend"):
            tgt_alt = maneuver.value
        elif maneuver.action == "turn":
            tgt_hdg = maneuver.value % 360.0
        elif maneuver.action == "speed":
            tgt_gs = maneuver.value
    out = [(x, y, alt)]
    for _ in range(horizon):
        if tgt_hdg is not None:
            d = heading_diff(tgt_hdg, hdg)
            hdg = (hdg + max(-TURN_RATE_DPS, min(TURN_RATE_DPS, d))) % 360.0
        if gs != tgt_gs:
            gs = tgt_gs if abs(tgt_gs - gs) <= SPEED_RATE_KTS else gs + math.copysign(SPEED_RATE_KTS, tgt_gs - gs)
        rate = (CLIMB_FPM if tgt_alt > alt else DESCENT_FPM) / 60.0
        alt = tgt_alt if abs(tgt_alt - alt) <= rate else alt + math.copysign(rate, tgt_alt - alt)
        vx, vy = velocity(hdg, gs)
        x, y = x + vx, y + vy
        out.append((x, y, alt))
    return out


def _on_final(ac: Aircraft) -> bool:
    return ac.land is not None and bool(ac.route) and ac.next_fix == ac.route[-1]


def suppressed(a: Aircraft, b: Aircraft) -> bool:
    return _on_final(a) and _on_final(b) and a.land != b.land


def probe_pair(a: Aircraft, b: Aircraft, maneuver: Optional[Maneuver] = None,
               horizon: int = LOOKAHEAD_S) -> Optional[Conflict]:
    ta = project(a, horizon, maneuver if maneuver and maneuver.callsign == a.callsign else None)
    tb = project(b, horizon, maneuver if maneuver and maneuver.callsign == b.callsign else None)
    t_los = None
    best = None  # (lateral, t, vertical)
    for t, ((xa, ya, za), (xb, yb, zb)) in enumerate(zip(ta, tb)):
        lat = math.hypot(xa - xb, ya - yb)
        vert = abs(za - zb)
        if lat < LATERAL_NM and vert < VERTICAL_FT:
            if t_los is None:
                t_los = t
            if best is None or lat < best[0]:
                best = (lat, t, vert)
    if t_los is None or best is None:
        return None
    lateral, t_cpa, vertical = best
    return Conflict(
        a=a.callsign,
        b=b.callsign,
        t_cpa=t_cpa,
        lateral_nm=lateral,
        vertical_ft=vertical,
        t_los=t_los,
        severity="imminent" if t_cpa < IMMINENT_S else "predicted",
    )


def probe(aircraft: Iterable[Aircraft], maneuver: Optional[Maneuver] = None) -> list[Conflict]:
    found = []
    for a, b in combinations(sorted(aircraft, key=lambda ac: ac.callsign), 2):
        if suppressed(a, b):
            continue
        c = probe_pair(a, b, maneuver)
        if c is not None:
            found.append(c)
    return found


def validate_maneuver(aircraft: Iterable[Aircraft], conflict_key: str, maneuver: Maneuver) -> tuple[bool, str]:
    """A suggestion is valid if it clears the target conflict and creates no new one
    for the maneuvering aircraft."""
    acs = list(aircraft)
    by_cs = {a.callsign: a for a in acs}
    if maneuver.callsign not in by_cs:
        return False, f"{maneuver.callsign} is not on the scope"
    if maneuver.callsign not in conflict_key.split("|"):
        return False, f"{maneuver.callsign} is not part of this conflict"
    for c in probe(acs, maneuver):
        if c.key == conflict_key:
            return False, "does not resolve the conflict"
        if maneuver.callsign in (c.a, c.b):
            other = c.b if c.a == maneuver.callsign else c.a
            return False, f"creates a new conflict with {other}"
    return True, "resolves the conflict with no new conflicts in 120 s"
