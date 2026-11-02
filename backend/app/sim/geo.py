"""Flat-earth local projection around the airport reference point.

Within ~60 nm of the ARP the error is negligible for a display and conflict probe.
x is nautical miles east, y is nautical miles north. Headings are degrees true,
0 = north, clockwise.
"""
from __future__ import annotations

import math

NM_PER_DEG_LAT = 60.0


class LocalProjection:
    def __init__(self, lat0: float, lon0: float) -> None:
        self.lat0 = lat0
        self.lon0 = lon0
        self.nm_per_deg_lon = NM_PER_DEG_LAT * math.cos(math.radians(lat0))

    def to_xy(self, lat: float, lon: float) -> tuple[float, float]:
        return (lon - self.lon0) * self.nm_per_deg_lon, (lat - self.lat0) * NM_PER_DEG_LAT

    def to_latlon(self, x: float, y: float) -> tuple[float, float]:
        return self.lat0 + y / NM_PER_DEG_LAT, self.lon0 + x / self.nm_per_deg_lon


def bearing(x0: float, y0: float, x1: float, y1: float) -> float:
    return math.degrees(math.atan2(x1 - x0, y1 - y0)) % 360.0


def distance(x0: float, y0: float, x1: float, y1: float) -> float:
    return math.hypot(x1 - x0, y1 - y0)


def velocity(heading_deg: float, gs_kt: float) -> tuple[float, float]:
    """Velocity in nm/s for a heading and groundspeed."""
    h = math.radians(heading_deg)
    return gs_kt * math.sin(h) / 3600.0, gs_kt * math.cos(h) / 3600.0


def heading_diff(target: float, current: float) -> float:
    """Signed shortest turn from current to target, in (-180, 180]."""
    d = (target - current + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d
