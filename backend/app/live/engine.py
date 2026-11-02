"""Live engine: same interface as SimEngine, driven by real ADS-B instead of a script.

Positions refresh from the feed every few seconds and are dead-reckoned at 1 Hz in
between so the scope moves smoothly. Only airborne traffic inside the terminal area
(radius, below FL180) is shown. Nothing here can move a real aircraft: controller
"approvals" in live mode are logged only.
"""
from __future__ import annotations

import math
import re
import time
from typing import Any, Optional

from ..sim.engine import SimEngine
from ..sim.geo import heading_diff
from ..sim.kinematics import Aircraft
from ..sim.scenario import Scenario
from .feed import Target

RADIUS_NM = 40
CEILING_FT = 17_500
STALE_S = 45
EAST_FLOW_IDS = {"26R": "8L", "27L": "9R", "28": "10"}
AIRLINE_RE = re.compile(r"^[A-Z]{3}\d")
APPROACH_AREA_NM = 18.0  # live: arrivals turning onto parallel finals look like collisions to a
APPROACH_AREA_FT = 7000.0  # straight-line probe; real controllers use visual/tower separation here
FINAL_MAX_NM = 20.0  # how far out an aircraft counts as established on final
FINAL_MAX_FT = 7000.0


def is_east_flow(wind_dir: Optional[float], wind_kt: Optional[float]) -> bool:
    """ATL runs east flow when the wind has an easterly component (light winds stay west)."""
    if wind_dir is None or wind_kt is None or wind_kt < 5:
        return False
    return math.cos(math.radians(wind_dir - 90)) > 0


class LiveEngine(SimEngine):
    # Real VFR traffic gets traffic advisories, not separation: don't raise conflict alerts for it.
    alert_on_vfr = False
    resolve_after_ticks = 10  # feed updates every 5 s; don't flap alerts on jitter
    # Real traffic is already separated by real controllers (visual approaches, reduced spacing on
    # final, sequencing) and we have no flight plans, so only flag genuinely close approaches.
    vertical_alert_ft = 500.0
    lateral_alert_nm = 1.5

    def __init__(self, base: Scenario) -> None:
        live = base.model_copy(update={
            "name": f"Live {base.airport.icao}", "description": "Real ADS-B traffic (adsb.lol / OpenSky)",
            "aircraft": [], "events": [], "duration_s": 10 ** 9,
        })
        self.provider = ""
        self.last_update: Optional[float] = None
        self.error = ""
        self.east_flow = False
        self.metar: dict[str, Any] = {}
        self.wx_fetched_at = 0.0
        self._seen: dict[str, float] = {}
        self._types: dict[str, dict[str, Any]] = {}
        super().__init__(live)

    def reset(self) -> None:
        super().reset()
        self._seen = {}

    def set_speed(self, speed: int) -> None:
        self.speed = 1  # real time only

    def tick(self) -> list:
        self.t += 1
        now = time.time()
        for cs in [cs for cs, seen in self._seen.items() if now - seen > STALE_S]:
            self.aircraft.pop(cs, None)
            self._seen.pop(cs, None)
        for ac in self.aircraft.values():
            # dead reckoning between feed updates
            ac.x += ac.gs_kt * math.sin(math.radians(ac.heading)) / 3600.0
            ac.y += ac.gs_kt * math.cos(math.radians(ac.heading)) / 3600.0
            ac.alt_ft = max(0.0, ac.alt_ft + ac.vs_fpm / 60.0)
        return []

    def update(self, targets: list[Target], provider: str) -> None:
        self.provider, self.last_update, self.error = provider, time.time(), ""
        now = time.time()
        placed: list[tuple[float, float, float]] = []
        for tg in sorted(targets, key=lambda t: t.age_s):
            x, y = self.proj.to_xy(tg.lat, tg.lon)
            if math.hypot(x, y) > RADIUS_NM or tg.alt_ft > CEILING_FT or tg.alt_ft < self.scenario.airport.elevation_ft + 200:
                continue
            cs = tg.callsign if tg.callsign not in self.aircraft or self._types.get(tg.callsign, {}).get("hex") == tg.hex \
                else f"{tg.callsign}-{tg.hex[-3:]}"
            # account for the age of the position report
            dt = min(tg.age_s, 10.0)
            x += tg.gs_kt * math.sin(math.radians(tg.track)) / 3600.0 * dt
            y += tg.gs_kt * math.cos(math.radians(tg.track)) / 3600.0 * dt
            if tg.selected_alt_ft and abs(tg.selected_alt_ft - tg.alt_ft) < 15_000:
                tgt_alt = round(tg.selected_alt_ft / 100) * 100
            elif abs(tg.vs_fpm) > 300:
                tgt_alt = tg.alt_ft + tg.vs_fpm  # ~1 minute of the current climb/descent
            else:
                tgt_alt = tg.alt_ft
            if any(abs(px - x) < 0.05 and abs(py - y) < 0.05 and abs(pz - tg.alt_ft) < 100 for px, py, pz in placed):
                continue  # same aircraft reported twice (e.g. ADS-B + MLAT)
            placed.append((x, y, tg.alt_ft))
            # ADS-B altitude is quantised and jittery: snap level aircraft to their 100 ft level so
            # two aircraft 1,000 ft apart don't read as 975 ft and trip the probe
            alt = round(tg.alt_ft / 100) * 100 if abs(tg.vs_fpm) < 300 else tg.alt_ft
            if abs(tg.vs_fpm) < 300 and abs(tgt_alt - alt) < 300:
                tgt_alt = alt
            self.aircraft[cs] = Aircraft(
                callsign=cs, type=tg.type, x=x, y=y, alt_ft=alt, heading=tg.track, gs_kt=tg.gs_kt,
                tgt_alt_ft=tgt_alt, tgt_gs_kt=tg.gs_kt, vs_fpm=tg.vs_fpm,
                flight_rules="VFR" if tg.squawk == "1200" else "IFR",
                # light aircraft and gliders mostly fly VFR/training with no separation standard
                probe_exempt=tg.category in ("A1", "A7") or tg.category.startswith("B")
                or (not tg.category and not AIRLINE_RE.match(tg.callsign))
                or (math.hypot(x, y) < APPROACH_AREA_NM and alt < APPROACH_AREA_FT),
            )
            self._types[cs] = {"hex": tg.hex, "squawk": tg.squawk}
            self._seen[cs] = now
        for ac in self.aircraft.values():
            rw = self.final_for(ac)
            ac.land, ac.route = (rw, [f"RW{rw}"]) if rw else (None, [])

    def landing_runways(self) -> list[tuple[str, tuple[float, float], float]]:
        """(runway id, threshold xy, landing course) for the current flow."""
        out = []
        for rw in self.scenario.runways:
            thr, end = self.proj.to_xy(rw.thr_lat, rw.thr_lon), self.proj.to_xy(rw.end_lat, rw.end_lon)
            rid = rw.id
            if self.east_flow:
                thr, end, rid = end, thr, EAST_FLOW_IDS.get(rw.id, rw.id)
            course = math.degrees(math.atan2(end[0] - thr[0], end[1] - thr[1])) % 360.0
            out.append((rid, thr, course))
        return out

    def final_for(self, ac: Aircraft) -> Optional[str]:
        """Runway the aircraft is established on final to, judged from its track and position."""
        if ac.alt_ft > FINAL_MAX_FT:
            return None
        best: Optional[tuple[float, str]] = None
        for rid, (tx, ty), course in self.landing_runways():
            ux, uy = math.sin(math.radians(course)), math.cos(math.radians(course))
            dx, dy = ac.x - tx, ac.y - ty
            along = -(dx * ux + dy * uy)  # nm out on final, before the threshold
            cross = abs(dx * uy - dy * ux)
            # generous enough to include aircraft still turning onto the localizer
            if 0 < along < FINAL_MAX_NM and cross < 1.0 + along * 0.05 and abs(heading_diff(course, ac.heading)) < 35:
                if best is None or cross < best[0]:
                    best = (cross, rid)  # parallels are ~1 nm apart: take the nearest centerline
        return best[1] if best else None

    def apply_action(self, callsign: str, action: str, value: float) -> None:
        raise PermissionError("live traffic cannot be controlled from Clearance")

    def static_view(self) -> dict[str, Any]:
        view = super().static_view()
        if self.east_flow:
            for rw in view["runways"]:
                rw["thr"], rw["end"] = rw["end"], rw["thr"]
                rw["id"] = EAST_FLOW_IDS.get(rw["id"], rw["id"])
        # the demo's fix names and sectors are illustrative: don't draw them over real traffic
        view["fixes"], view["sectors"] = [], []
        view["live"] = True
        view["flow"] = "east" if self.east_flow else "west"
        return view

    def snapshot(self) -> dict[str, Any]:
        snap = super().snapshot()
        snap["finished"] = False
        snap["live"] = {
            "provider": self.provider, "error": self.error, "flow": "east" if self.east_flow else "west",
            "age_s": round(time.time() - self.last_update) if self.last_update else None,
            "metar": self.metar.get("metar", ""),
        }
        return snap
