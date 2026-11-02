"""Generate atl_arrivals_demo.json and report every conflict the probe sees.

Run:  python -m scenarios.build_demo   (from backend/)

Geometry is authored in nm east/north of the ATL reference point and written
out as lat/lon. Fix names other than runways are illustrative, not real
procedure fixes.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from app.conflict.probe import probe
from app.sim.engine import SimEngine
from app.sim.geo import LocalProjection
from app.sim.scenario import Scenario

ARP = (33.6367, -84.4281)
P = LocalProjection(*ARP)
OUT = Path(__file__).with_name("atl_arrivals_demo.json")


def ll(x: float, y: float) -> tuple[float, float]:
    lat, lon = P.to_latlon(x, y)
    return round(lat, 5), round(lon, 5)


def behind(fix: tuple[float, float], from_bearing: float, gs_kt: float, seconds: float) -> tuple[float, float]:
    """Point that reaches `fix` after `seconds` flying toward it from `from_bearing`."""
    d = gs_kt * seconds / 3600.0
    b = math.radians(from_bearing)
    return fix[0] + d * math.sin(b), fix[1] + d * math.cos(b)


# Westflow: landing 26R / 27L / 28 (thresholds on the east end).
RUNWAYS = {
    "26R": ((0.92, 0.78), (-0.55, 0.78)),
    "27L": ((0.49, -0.29), (-1.20, -0.29)),
    "28": ((0.90, -1.00), (-0.88, -1.00)),
}
FIXES = {
    "RW26R": (0.92, 0.78, "runway"),
    "RW27L": (0.49, -0.29, "runway"),
    "RW28": (0.90, -1.00, "runway"),
    "DOOLY": (12.9, 0.78, "faf"),  # 26R final
    "PRYOR": (12.5, -0.29, "faf"),  # 27L final
    "TAXUS": (12.9, -1.00, "faf"),  # 28 final
    "ROSWL": (14.0, 10.0, "fix"),  # north downwind
    "LOGAN": (16.0, -12.0, "fix"),  # south downwind
    "FALCN": (-18.0, 6.0, "fix"),  # west arrival gate
    "CHERO": (0.0, 14.0, "fix"),  # north side transition
    "DAWGS": (28.0, 28.0, "fix"),  # NE corner post
    "PEACH": (28.0, -28.0, "fix"),  # SE corner post
    "HAWKS": (-28.0, 28.0, "fix"),  # NW corner post
    "BRAVS": (-28.0, -28.0, "fix"),  # SW corner post
}


def fix_xy(fid: str) -> tuple[float, float]:
    return FIXES[fid][0], FIXES[fid][1]


def heading_to(src: tuple[float, float], fid: str) -> float:
    fx, fy = fix_xy(fid)
    return round(math.degrees(math.atan2(fx - src[0], fy - src[1])) % 360.0, 1)


def ac(callsign, typ, xy, alt, gs, route, land=None, **kw):
    lat, lon = ll(*xy)
    return {
        "callsign": callsign,
        "type": typ,
        "lat": lat,
        "lon": lon,
        "alt_ft": alt,
        "heading": kw.pop("heading", heading_to(xy, route[0])),
        "gs_kt": gs,
        "route": route,
        "land": land,
        **kw,
    }


def build() -> dict:
    roswl = fix_xy("ROSWL")
    # The scripted conflict: both cleared direct ROSWL at 8,000 and arriving together.
    dal1423 = behind(roswl, 45, 250, 257)
    swa2210 = behind(roswl, 350, 260, 255)
    dal1066 = behind(roswl, 45, 250, 257 + 150)

    aircraft = [
        ac("AAL1187", "A321", (10.9, 0.78), 4000, 180, ["RW26R"], "26R", heading=270, origin="KDFW", destination="KATL"),
        ac("DAL892", "A21N", (17.5, -0.29), 5000, 210, ["RW27L"], "27L", heading=270, origin="KMCO", destination="KATL"),
        ac("UAL455", "B738", (15.5, -9.5), 6000, 220, ["TAXUS", "RW28"], "28", assigned_alt_ft=5000, origin="KIAH", destination="KATL"),
        ac("DAL1423", "B739", dal1423, 8000, 250, ["ROSWL", "DOOLY", "RW26R"], "26R", origin="KBOS", destination="KATL"),
        ac("SWA2210", "B38M", swa2210, 8000, 260, ["ROSWL", "DOOLY", "RW26R"], "26R", origin="KMDW", destination="KATL"),
        ac("DAL1066", "B712", dal1066, 12000, 250, ["ROSWL", "DOOLY", "RW26R"], "26R", origin="KLGA", destination="KATL"),
        ac("DAL2290", "B752", (32.0, -24.0), 11000, 280, ["LOGAN", "PRYOR", "RW27L"], "27L",
           clearances=[{"t": 60, "alt_ft": 9000, "note": "descend via profile"}], origin="KMIA", destination="KATL"),
        ac("SWA1784", "B737", (-24.0, -22.0), 12000, 270, ["LOGAN", "TAXUS", "RW28"], "28", heading=75, origin="KMSY", destination="KATL"),
        ac("UAL1712", "B39M", (-34.0, 14.0), 10000, 280, ["FALCN", "CHERO"], None, origin="KDEN", destination="KATL"),
        ac("N451GA", "GLF4", (-30.0, 20.0), 9000, 300, ["FALCN", "CHERO"], None, spawn_t=20, origin="KTEB", destination="KPDK"),
        ac("AAL2541", "A319", (-40.0, 24.0), 11000, 290, ["FALCN", "CHERO"], None, spawn_t=40, origin="KPHX", destination="KATL"),
        ac("N172SP", "C172", (-6.0, 16.0), 3500, 100, ["HAWKS"], None, flight_rules="VFR", origin="KFTY", destination="KRMG"),
    ]

    wx_center = (-16.0, 3.0)
    wx_poly = [
        ll(wx_center[0] + r * math.sin(math.radians(a)), wx_center[1] + r * math.cos(math.radians(a)))
        for a, r in [(0, 6.0), (40, 5.0), (80, 4.2), (120, 5.5), (160, 6.5), (200, 5.0), (240, 4.5), (280, 6.0), (320, 5.2)]
    ]

    return {
        "name": "ATL Westflow Arrivals — demo",
        "description": "Twelve arrivals into Atlanta, westflow (26R/27L/28). Scripted converging pair at T+90, "
                       "weather cell west of the field at T+150, position relief at T+210.",
        "facility": "A80 (Atlanta TRACON)",
        "position": "Final/Arrival — west flow",
        "airport": {"icao": "KATL", "name": "Hartsfield–Jackson Atlanta Intl", "lat": ARP[0], "lon": ARP[1], "elevation_ft": 1026},
        "runways": [
            {"id": rid, "thr_lat": ll(*thr)[0], "thr_lon": ll(*thr)[1], "end_lat": ll(*end)[0], "end_lon": ll(*end)[1]}
            for rid, (thr, end) in RUNWAYS.items()
        ],
        "fixes": [{"id": fid, "lat": ll(x, y)[0], "lon": ll(x, y)[1], "kind": kind} for fid, (x, y, kind) in FIXES.items()],
        "sectors": [
            {"id": "N", "name": "North arrival", "polygon": [ll(-30, 3), ll(-30, 30), ll(30, 30), ll(30, 3)]},
            {"id": "S", "name": "South arrival", "polygon": [ll(-30, -3), ll(-30, -30), ll(30, -30), ll(30, -3)]},
        ],
        "duration_s": 360,
        "aircraft": aircraft,
        "events": [
            {"t": 0, "kind": "shift_start", "title": "Shift start", "detail": "Day shift, A80 arrival position opens."},
            {"t": 150, "kind": "weather", "title": "Convective cell west of field",
             "detail": "Heavy precipitation developing over FALCN, moving ENE ~15 kt.",
             "polygon": wx_poly, "intensity": "heavy", "drift_kt": 15, "drift_heading": 70, "affects_fix": "FALCN"},
            {"t": 210, "kind": "relief", "title": "Position relief", "detail": "Relieving controller plugs in."},
            {"t": 355, "kind": "shift_end", "title": "End of shift", "detail": "Position closes; paperwork due."},
        ],
    }


def report(data: dict) -> None:
    eng = SimEngine(Scenario.model_validate(data))
    seen: dict[str, int] = {}
    while not eng.finished:
        for ev in eng.tick():
            print(f"T+{ev.t:3d}s event {ev.kind}")
        for c in probe(eng.aircraft.values()):
            if c.key not in seen:
                seen[c.key] = eng.t
                print(f"T+{eng.t:3d}s conflict {c.key} {c.severity} cpa={c.t_cpa}s {c.lateral_nm:.2f}nm {c.vertical_ft:.0f}ft")
    for l in eng.landed:
        print(f"T+{l['t']:3d}s landed {l['callsign']} {l['runway']}")


def add_popup(data: dict) -> None:
    """Pop-up VFR target (just climbed into radar coverage) crossing DAL2290's path at
    8,500 ft. Imminent the moment it appears, so the shift has an incident to report."""
    eng = SimEngine(Scenario.model_validate(data))
    eng.run_until(POPUP_T + POPUP_CPA_S)
    tgt = eng.aircraft["DAL2290"]
    bx, by = fix_xy("BRAVS")
    to_bravs = math.degrees(math.atan2(bx - tgt.x, by - tgt.y)) % 360.0
    start = behind((tgt.x, tgt.y), (to_bravs + 180.0) % 360.0, 120, POPUP_CPA_S)
    data["aircraft"].append(ac("N8734K", "PA28", start, 8500, 120, ["BRAVS"], None, spawn_t=POPUP_T,
                               flight_rules="VFR", origin="KLZU", destination="KLGC"))


POPUP_T = 240
POPUP_CPA_S = 40


if __name__ == "__main__":
    d = build()
    add_popup(d)
    OUT.write_text(json.dumps(d, indent=2) + "\n")
    print(f"wrote {OUT}")
    report(d)
