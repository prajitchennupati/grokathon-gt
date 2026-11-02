"""Scenario file format.

A scenario is plain JSON validated by these models. Positions are lat/lon,
altitudes are feet MSL, speeds are knots groundspeed, headings degrees true.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Airport(BaseModel):
    icao: str
    name: str = ""
    lat: float
    lon: float
    elevation_ft: float = 0.0


class Runway(BaseModel):
    """One landing direction. `thr_*` is the landing threshold, `end_*` the far end."""

    id: str
    thr_lat: float
    thr_lon: float
    end_lat: float
    end_lon: float
    active: bool = True
    final_nm: float = 15.0  # length of the extended centerline drawn on the scope


class Fix(BaseModel):
    id: str
    lat: float
    lon: float
    kind: Literal["fix", "faf", "runway"] = "fix"


class Sector(BaseModel):
    id: str
    name: str
    polygon: list[tuple[float, float]]  # [(lat, lon), ...]


class Clearance(BaseModel):
    """A timed instruction applied to one aircraft. Any field left None is unchanged.

    `heading` puts the aircraft on a vector (it stops following its route);
    `direct` sends it direct to a fix and resumes the route from there.
    """

    t: int
    heading: Optional[float] = None
    turn: Optional[Literal["left", "right"]] = None
    alt_ft: Optional[float] = None
    gs_kt: Optional[float] = None
    direct: Optional[str] = None
    note: str = ""


class AircraftSpec(BaseModel):
    callsign: str
    type: str
    lat: float
    lon: float
    alt_ft: float
    heading: float
    gs_kt: float
    spawn_t: int = 0
    route: list[str] = Field(default_factory=list)  # fix ids flown in order
    land: Optional[str] = None  # runway id; aircraft is removed at the threshold
    assigned_alt_ft: Optional[float] = None
    clearances: list[Clearance] = Field(default_factory=list)
    flight_rules: Literal["IFR", "VFR"] = "IFR"
    origin: str = ""
    destination: str = ""


class ScenarioEvent(BaseModel):
    t: int
    kind: Literal["shift_start", "weather", "relief", "shift_end", "note"]
    title: str = ""
    detail: str = ""
    # weather only
    polygon: list[tuple[float, float]] = Field(default_factory=list)  # [(lat, lon), ...]
    intensity: Literal["light", "moderate", "heavy", "extreme"] = "heavy"
    drift_kt: float = 0.0
    drift_heading: float = 0.0
    affects_fix: Optional[str] = None


class Scenario(BaseModel):
    name: str
    description: str = ""
    facility: str = "A80"
    position: str = ""
    airport: Airport
    runways: list[Runway]
    fixes: list[Fix] = Field(default_factory=list)
    sectors: list[Sector] = Field(default_factory=list)
    duration_s: int = 360
    aircraft: list[AircraftSpec]
    events: list[ScenarioEvent] = Field(default_factory=list)


def load_scenario(path: str | Path) -> Scenario:
    return Scenario.model_validate(json.loads(Path(path).read_text()))
