"""Scenario replay engine: owns sim time, aircraft and scripted events."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from .geo import LocalProjection
from .kinematics import Aircraft, step
from .scenario import AircraftSpec, Clearance, Scenario, ScenarioEvent


@dataclass
class WeatherCell:
    id: str
    title: str
    intensity: str
    polygon_xy: list[tuple[float, float]]
    drift_vx: float  # nm/s
    drift_vy: float
    appeared_t: int
    affects_fix: Optional[str] = None


@dataclass
class FiredEvent:
    t: int
    kind: str
    title: str
    detail: str
    data: dict[str, Any] = field(default_factory=dict)


class SimEngine:
    SPEEDS = (1, 2, 4)

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.proj = LocalProjection(scenario.airport.lat, scenario.airport.lon)
        self.fixes_xy: dict[str, tuple[float, float]] = {
            f.id: self.proj.to_xy(f.lat, f.lon) for f in scenario.fixes
        }
        self.running = False
        self.speed = 1
        self.reset()

    # ---- lifecycle -------------------------------------------------------
    def reset(self) -> None:
        self.t = 0
        self.aircraft: dict[str, Aircraft] = {}
        self.landed: list[dict[str, Any]] = []
        self.weather: list[WeatherCell] = []
        self.fired: list[FiredEvent] = []
        self._pending_spawn = sorted(self.scenario.aircraft, key=lambda a: a.spawn_t)
        self._clearances: list[tuple[str, Clearance]] = sorted(
            ((a.callsign, c) for a in self.scenario.aircraft for c in a.clearances), key=lambda p: p[1].t
        )
        self._events = sorted(self.scenario.events, key=lambda e: e.t)
        self._spawn_due()
        self._fire_due()  # t=0 events (shift start)

    @property
    def finished(self) -> bool:
        return self.t >= self.scenario.duration_s

    def tick(self) -> list[FiredEvent]:
        """Advance one second. Returns scripted events that fired this tick."""
        if self.finished:
            return []
        self.t += 1
        for cs, clr in self._take_due_clearances():
            if cs in self.aircraft:
                self.apply_clearance(self.aircraft[cs], clr)
        for ac in list(self.aircraft.values()):
            step(ac, self.fixes_xy, self.scenario.airport.elevation_ft)
            if ac.landed:
                del self.aircraft[ac.callsign]
                self.landed.append({"callsign": ac.callsign, "runway": ac.land, "t": self.t})
        for cell in self.weather:
            cell.polygon_xy = [(x + cell.drift_vx, y + cell.drift_vy) for x, y in cell.polygon_xy]
        self._spawn_due()
        return self._fire_due()

    def run_until(self, t: int) -> list[FiredEvent]:
        fired: list[FiredEvent] = []
        while self.t < min(t, self.scenario.duration_s):
            fired += self.tick()
        return fired

    # ---- control ---------------------------------------------------------
    def set_speed(self, speed: int) -> None:
        if speed not in self.SPEEDS:
            raise ValueError(f"speed must be one of {self.SPEEDS}")
        self.speed = speed

    def apply_clearance(self, ac: Aircraft, clr: Clearance) -> None:
        if clr.alt_ft is not None:
            ac.tgt_alt_ft = clr.alt_ft
        if clr.gs_kt is not None:
            ac.tgt_gs_kt = clr.gs_kt
        if clr.heading is not None:
            ac.tgt_heading = clr.heading % 360.0
            ac.turn_dir = clr.turn
        if clr.direct is not None and clr.direct in ac.route:
            ac.tgt_heading = None
            ac.turn_dir = None
            ac.route_idx = ac.route.index(clr.direct)

    def apply_action(self, callsign: str, action: str, value: float) -> None:
        """Apply a controller-approved instruction (simulates pilot compliance)."""
        ac = self.aircraft.get(callsign)
        if ac is None:
            raise KeyError(callsign)
        if action in ("climb", "descend"):
            self.apply_clearance(ac, Clearance(t=self.t, alt_ft=value))
        elif action == "turn":
            self.apply_clearance(ac, Clearance(t=self.t, heading=value))
        elif action == "speed":
            self.apply_clearance(ac, Clearance(t=self.t, gs_kt=value))
        else:
            raise ValueError(action)

    # ---- internals -------------------------------------------------------
    def _make_aircraft(self, spec: AircraftSpec) -> Aircraft:
        x, y = self.proj.to_xy(spec.lat, spec.lon)
        return Aircraft(
            callsign=spec.callsign,
            type=spec.type,
            x=x,
            y=y,
            alt_ft=spec.alt_ft,
            heading=spec.heading,
            gs_kt=spec.gs_kt,
            tgt_alt_ft=spec.assigned_alt_ft if spec.assigned_alt_ft is not None else spec.alt_ft,
            tgt_gs_kt=spec.gs_kt,
            route=list(spec.route),
            land=spec.land,
            flight_rules=spec.flight_rules,
            origin=spec.origin,
            destination=spec.destination,
        )

    def _spawn_due(self) -> None:
        while self._pending_spawn and self._pending_spawn[0].spawn_t <= self.t:
            spec = self._pending_spawn.pop(0)
            self.aircraft[spec.callsign] = self._make_aircraft(spec)

    def _take_due_clearances(self) -> list[tuple[str, Clearance]]:
        due = []
        while self._clearances and self._clearances[0][1].t <= self.t:
            due.append(self._clearances.pop(0))
        return due

    def _fire_due(self) -> list[FiredEvent]:
        fired = []
        while self._events and self._events[0].t <= self.t:
            fired.append(self._fire(self._events.pop(0)))
        return fired

    def _fire(self, ev: ScenarioEvent) -> FiredEvent:
        data: dict[str, Any] = {}
        if ev.kind == "weather":
            h = math.radians(ev.drift_heading)
            cell = WeatherCell(
                id=f"wx{len(self.weather) + 1}",
                title=ev.title,
                intensity=ev.intensity,
                polygon_xy=[self.proj.to_xy(lat, lon) for lat, lon in ev.polygon],
                drift_vx=ev.drift_kt * math.sin(h) / 3600.0,
                drift_vy=ev.drift_kt * math.cos(h) / 3600.0,
                appeared_t=self.t,
                affects_fix=ev.affects_fix,
            )
            self.weather.append(cell)
            data = {"cell_id": cell.id, "affects_fix": ev.affects_fix, "intensity": ev.intensity}
        fe = FiredEvent(t=self.t, kind=ev.kind, title=ev.title, detail=ev.detail, data=data)
        self.fired.append(fe)
        return fe

    # ---- output ----------------------------------------------------------
    def aircraft_view(self, ac: Aircraft) -> dict[str, Any]:
        lat, lon = self.proj.to_latlon(ac.x, ac.y)
        return {
            "callsign": ac.callsign,
            "type": ac.type,
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "x": round(ac.x, 3),
            "y": round(ac.y, 3),
            "alt_ft": round(ac.alt_ft),
            "tgt_alt_ft": round(ac.tgt_alt_ft),
            "heading": round(ac.heading, 1),
            "gs_kt": round(ac.gs_kt),
            "vs_fpm": round(ac.vs_fpm),
            "next_fix": ac.next_fix,
            "vector": ac.tgt_heading is not None,
            "land": ac.land,
            "flight_rules": ac.flight_rules,
            "origin": ac.origin,
            "destination": ac.destination,
        }

    def static_view(self) -> dict[str, Any]:
        s = self.scenario
        return {
            "name": s.name,
            "description": s.description,
            "facility": s.facility,
            "position": s.position,
            "airport": s.airport.model_dump(),
            "duration_s": s.duration_s,
            "runways": [
                {
                    **r.model_dump(),
                    "thr": self.proj.to_xy(r.thr_lat, r.thr_lon),
                    "end": self.proj.to_xy(r.end_lat, r.end_lon),
                }
                for r in s.runways
            ],
            "fixes": [{"id": f.id, "kind": f.kind, "xy": self.fixes_xy[f.id]} for f in s.fixes],
            "sectors": [
                {"id": sec.id, "name": sec.name, "polygon_xy": [self.proj.to_xy(a, b) for a, b in sec.polygon]}
                for sec in s.sectors
            ],
            "events": [{"t": e.t, "kind": e.kind, "title": e.title} for e in s.events],
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "t": self.t,
            "duration_s": self.scenario.duration_s,
            "running": self.running and not self.finished,
            "finished": self.finished,
            "speed": self.speed,
            "aircraft": [self.aircraft_view(a) for a in self.aircraft.values()],
            "landed": self.landed[-10:],
            "weather": [
                {
                    "id": c.id,
                    "title": c.title,
                    "intensity": c.intensity,
                    "polygon_xy": [(round(x, 3), round(y, 3)) for x, y in c.polygon_xy],
                    "affects_fix": c.affects_fix,
                }
                for c in self.weather
            ],
            "events_fired": [e.__dict__ for e in self.fired],
        }
