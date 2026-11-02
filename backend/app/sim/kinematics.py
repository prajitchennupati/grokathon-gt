"""Deterministic 1 Hz aircraft kinematics.

Standard-rate turns, fixed climb/descent rates and linear speed changes. Route
following flies direct to each fix in turn; aircraft cleared to land track a
3-degree glidepath to the threshold and are removed there.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .geo import bearing, distance, heading_diff, velocity

TURN_RATE_DPS = 3.0  # standard rate
CLIMB_FPM = 1500.0
DESCENT_FPM = 2000.0
SPEED_RATE_KTS = 1.5  # kt per second
GLIDEPATH_FT_PER_NM = 318.0  # 3 degrees
FIX_CAPTURE_NM = 1.0
THRESHOLD_CAPTURE_NM = 0.4
FINAL_APPROACH_SPEED_KT = 145.0


@dataclass
class Aircraft:
    callsign: str
    type: str
    x: float
    y: float
    alt_ft: float
    heading: float
    gs_kt: float
    tgt_alt_ft: float
    tgt_heading: Optional[float] = None  # set => on a vector, route ignored
    turn_dir: Optional[str] = None  # forced turn direction for the current vector
    tgt_gs_kt: float = 0.0
    route: list[str] = field(default_factory=list)
    route_idx: int = 0
    land: Optional[str] = None
    flight_rules: str = "IFR"
    vs_fpm: float = 0.0
    landed: bool = False
    origin: str = ""
    destination: str = ""
    probe_exempt: bool = False  # e.g. light GA in live mode: shown, but not conflict-probed

    @property
    def next_fix(self) -> Optional[str]:
        if self.tgt_heading is not None or self.route_idx >= len(self.route):
            return None
        return self.route[self.route_idx]

    def copy(self) -> "Aircraft":
        return Aircraft(**{**self.__dict__, "route": list(self.route)})


def _toward(current: float, target: float, max_step: float) -> float:
    if abs(target - current) <= max_step:
        return target
    return current + max_step if target > current else current - max_step


def step(ac: Aircraft, fixes: dict[str, tuple[float, float]], runway_elev_ft: float = 0.0, dt: float = 1.0) -> None:
    """Advance one aircraft by dt seconds in place."""
    tgt_alt = ac.tgt_alt_ft
    tgt_gs = ac.tgt_gs_kt
    desired_hdg = ac.tgt_heading

    fix_id = ac.next_fix
    if fix_id is not None and fix_id in fixes:
        fx, fy = fixes[fix_id]
        dist = distance(ac.x, ac.y, fx, fy)
        is_threshold = ac.land is not None and fix_id == ac.route[-1]
        if is_threshold:
            # On final: glidepath and approach speed schedule.
            tgt_alt = min(tgt_alt, runway_elev_ft + 50.0 + dist * GLIDEPATH_FT_PER_NM)
            tgt_gs = min(tgt_gs, FINAL_APPROACH_SPEED_KT + max(0.0, dist - 4.0) * 12.0)
            if dist < THRESHOLD_CAPTURE_NM:
                ac.landed = True
                return
        elif dist < FIX_CAPTURE_NM:
            ac.route_idx += 1
            fix_id = ac.next_fix
            if fix_id is not None and fix_id in fixes:
                fx, fy = fixes[fix_id]
        if fix_id is not None and fix_id in fixes:
            desired_hdg = bearing(ac.x, ac.y, fx, fy)

    if desired_hdg is not None:
        diff = heading_diff(desired_hdg, ac.heading)
        if ac.tgt_heading is not None and ac.turn_dir and abs(diff) > TURN_RATE_DPS * dt:
            diff = abs(diff) if ac.turn_dir == "right" else -abs(diff)
        turn = max(-TURN_RATE_DPS * dt, min(TURN_RATE_DPS * dt, diff))
        ac.heading = (ac.heading + turn) % 360.0
        if ac.tgt_heading is not None and abs(heading_diff(ac.tgt_heading, ac.heading)) < 1e-6:
            ac.turn_dir = None

    ac.gs_kt = _toward(ac.gs_kt, tgt_gs, SPEED_RATE_KTS * dt)

    rate = CLIMB_FPM if tgt_alt > ac.alt_ft else DESCENT_FPM
    new_alt = _toward(ac.alt_ft, tgt_alt, rate / 60.0 * dt)
    ac.vs_fpm = (new_alt - ac.alt_ft) / dt * 60.0
    ac.alt_ft = new_alt

    vx, vy = velocity(ac.heading, ac.gs_kt)
    ac.x += vx * dt
    ac.y += vy * dt
