"""Live ADS-B traffic around the airport from free, keyless sources.

Primary: adsb.lol (open data, ODbL; readsb JSON). Backup: OpenSky Network anonymous REST.
Both are rate-limited community services: poll no faster than every few seconds.
Flightradar24 is not used: its data is licensed and scraping it violates its terms.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger("clearance.live")

UA = {"User-Agent": "clearance-atc-prototype/0.1 (hackathon; advisory only)"}
M_TO_FT = 3.28084
MS_TO_KT = 1.943844
MS_TO_FPM = 196.850394


@dataclass
class Target:
    hex: str
    callsign: str
    type: str
    lat: float
    lon: float
    alt_ft: float
    gs_kt: float
    track: float
    vs_fpm: float
    selected_alt_ft: Optional[float]  # autopilot/MCP altitude when the aircraft broadcasts it
    squawk: str
    age_s: float  # seconds since the position was received
    category: str = ""  # ADS-B emitter category: A1 light ... A5 heavy, B* gliders/balloons/UAV


def _readsb(data: dict) -> list[Target]:
    out = []
    for a in data.get("ac", []):
        alt = a.get("alt_baro")
        if a.get("lat") is None or a.get("lon") is None or alt in (None, "ground"):
            continue
        if a.get("gs") is None or a.get("track") is None:
            continue
        out.append(Target(
            hex=a["hex"], callsign=(a.get("flight") or a.get("r") or a["hex"]).strip(), type=a.get("t") or "UNKN",
            lat=a["lat"], lon=a["lon"], alt_ft=float(alt), gs_kt=float(a["gs"]), track=float(a["track"]),
            vs_fpm=float(a.get("baro_rate") or a.get("geom_rate") or 0),
            selected_alt_ft=float(a["nav_altitude_mcp"]) if a.get("nav_altitude_mcp") else None,
            squawk=a.get("squawk") or "", age_s=float(a.get("seen_pos") or 0), category=a.get("category") or "",
        ))
    return out


def _opensky(data: dict, now: float) -> list[Target]:
    out = []
    for s in data.get("states") or []:
        (icao, cs, _country, t_pos, _last, lon, lat, baro_m, on_ground, vel, track, vr, _sens, geo_m, squawk, *_rest) = s
        if lat is None or lon is None or on_ground or vel is None or track is None:
            continue
        alt_m = baro_m if baro_m is not None else geo_m
        if alt_m is None:
            continue
        out.append(Target(
            hex=icao, callsign=(cs or icao).strip() or icao, type="UNKN", lat=lat, lon=lon, alt_ft=alt_m * M_TO_FT,
            gs_kt=vel * MS_TO_KT, track=float(track), vs_fpm=(vr or 0) * MS_TO_FPM, selected_alt_ft=None,
            squawk=squawk or "", age_s=max(0.0, now - (t_pos or now)),
        ))
    return out


async def fetch(lat: float, lon: float, radius_nm: float, client: httpx.AsyncClient) -> tuple[list[Target], str]:
    """Returns (targets, provider name). Raises if every provider fails."""
    errors = []
    try:
        r = await client.get(f"https://api.adsb.lol/v2/point/{lat:.4f}/{lon:.4f}/{int(radius_nm)}", headers=UA, timeout=6)
        r.raise_for_status()
        return _readsb(r.json()), "adsb.lol"
    except Exception as e:
        errors.append(f"adsb.lol: {type(e).__name__}")
    try:
        dlat, dlon = radius_nm / 60.0, radius_nm / 50.0
        r = await client.get("https://opensky-network.org/api/states/all", headers=UA, timeout=8, params={
            "lamin": lat - dlat, "lamax": lat + dlat, "lomin": lon - dlon, "lomax": lon + dlon})
        r.raise_for_status()
        data = r.json()
        return _opensky(data, float(data.get("time") or 0)), "OpenSky"
    except Exception as e:
        errors.append(f"OpenSky: {type(e).__name__}")
    raise RuntimeError("; ".join(errors))


async def fetch_metar_taf(icao: str, client: httpx.AsyncClient) -> dict:
    """Real METAR/TAF from aviationweather.gov. Each key is present only if its fetch succeeded."""
    out: dict = {}
    try:
        m = await client.get("https://aviationweather.gov/api/data/metar", params={"ids": icao, "format": "json"}, headers=UA, timeout=8)
        m.raise_for_status()
        if m.json():
            j = m.json()[0]
            out.update(metar=j.get("rawOb", ""), wind_dir=j.get("wdir"), wind_kt=j.get("wspd"))
    except Exception as e:
        log.warning("METAR fetch failed: %s", e)
    try:
        t = await client.get("https://aviationweather.gov/api/data/taf", params={"ids": icao, "format": "json"}, headers=UA, timeout=8)
        t.raise_for_status()
        if t.json():
            out["taf"] = t.json()[0].get("rawTAF", "")
    except Exception as e:
        log.warning("TAF fetch failed: %s", e)
    return out
