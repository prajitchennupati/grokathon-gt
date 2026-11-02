"""Optional: convert recorded ADS-B tracks (OpenSky-style CSV) into a scenario.

    python -m app.sim.adsb tracks.csv scenarios/recorded.json --base scenarios/atl_arrivals_demo.json

CSV columns: time, icao24, callsign, lat, lon, baro_altitude (m), velocity (m/s), heading.
Each track's first row becomes the initial state; later rows become timed clearances
(heading / altitude / speed targets), so the replay follows the recorded track
closely without needing per-second positions. Airport, runways and fixes are copied
from --base. Offline only: this never touches a live feed.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

M_TO_FT = 3.28084
MS_TO_KT = 1.943844


def convert(csv_path: Path, base: dict, sample_s: int = 10, max_aircraft: int = 40) -> dict:
    tracks: dict[str, list[dict]] = defaultdict(list)
    with csv_path.open() as fh:
        for row in csv.DictReader(fh):
            try:
                rec = {
                    "time": int(float(row["time"])),
                    "callsign": (row.get("callsign") or row["icao24"]).strip() or row["icao24"],
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "alt_ft": float(row["baro_altitude"]) * M_TO_FT,
                    "gs_kt": float(row["velocity"]) * MS_TO_KT,
                    "heading": float(row["heading"]),
                }
            except (KeyError, ValueError):
                continue  # gaps in recorded data are common
            tracks[row["icao24"]].append(rec)
    if not tracks:
        raise ValueError("no usable rows in CSV")

    t0 = min(r["time"] for rows in tracks.values() for r in rows)
    t_end = max(r["time"] for rows in tracks.values() for r in rows)
    aircraft = []
    for rows in list(tracks.values())[:max_aircraft]:
        rows.sort(key=lambda r: r["time"])
        first = rows[0]
        clearances, last_t = [], -sample_s
        for r in rows[1:]:
            rel = r["time"] - t0
            if rel - last_t < sample_s:
                continue
            last_t = rel
            clearances.append({"t": rel, "heading": round(r["heading"], 1), "alt_ft": round(r["alt_ft"]), "gs_kt": round(r["gs_kt"])})
        aircraft.append({
            "callsign": first["callsign"],
            "type": "UNKN",
            "lat": first["lat"],
            "lon": first["lon"],
            "alt_ft": round(first["alt_ft"]),
            "heading": round(first["heading"], 1),
            "gs_kt": round(first["gs_kt"]),
            "spawn_t": first["time"] - t0,
            "clearances": clearances,
        })
    return {
        **{k: base[k] for k in ("airport", "runways", "fixes", "sectors", "facility", "position")},
        "name": f"Recorded ADS-B: {csv_path.name}",
        "description": "Converted from recorded ADS-B tracks.",
        "duration_s": t_end - t0,
        "aircraft": aircraft,
        "events": [{"t": 0, "kind": "shift_start", "title": "Shift start"}],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--base", type=Path, required=True, help="scenario to copy airport/runways/fixes from")
    ap.add_argument("--sample", type=int, default=10, help="seconds between clearances")
    args = ap.parse_args()
    data = convert(args.csv, json.loads(args.base.read_text()), args.sample)
    args.out.write_text(json.dumps(data, indent=2))
    print(f"wrote {args.out}: {len(data['aircraft'])} aircraft, {data['duration_s']} s")


if __name__ == "__main__":
    main()
