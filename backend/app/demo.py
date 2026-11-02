"""The scripted demo: presenter-paced steps through one shift."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import AppState

STEPS: list[dict[str, Any]] = [
    {"id": "shift_start", "caption": "A new shift starts. The Briefing helper has summed up the weather and airport status.", "t": 1, "title": "Shift start → briefing",
     "say": "Briefing Bot pulled METAR/TAF, NOTAMs, closures and flow restrictions into one page."},
    {"id": "conflict", "caption": "Two planes are heading for the same spot at the same height. Clearance suggests a fix; the controller approves it.", "t": 91, "title": "Conflict + approval",
     "say": "The deterministic probe flags DAL1423 / SWA2210 two minutes out. Grok explains it and picks a "
            "probe-verified fix. Nothing happens until the controller presses A."},
    {"id": "weather", "caption": "A storm has formed west of the airport. A helper drafted warnings to the neighbouring control centre.", "t": 150, "title": "Weather + coordination",
     "say": "A cell builds over FALCN. Coordination Bot drafts a miles-in-trail request to Atlanta Center. "
            "It sits in the approval queue; approving only simulates the send."},
    {"id": "relief", "caption": "Controllers are swapping seats. A helper wrote the handover checklist for the new controller.", "t": 210, "title": "Relief briefing",
     "say": "Relief Bot turns the live picture into a checklist; the incoming controller ACKs each item."},
    {"id": "popup", "caption": "A small plane appeared without warning. There's no safe automatic fix, so Clearance says so.", "t": 240, "title": "Pop-up VFR (imminent)",
     "say": "A VFR target pops up 40 s from DAL2290. No single maneuver passes the probe, so Clearance says "
            "so instead of guessing."},
    {"id": "shift_end", "caption": "End of shift. A helper wrote the shift report and an incident report.", "t": 355, "title": "End-of-shift paperwork",
     "say": "Paperwork Bot writes the shift summary and a draft incident report for the imminent conflict. "
            "Export as PDF."},
]


async def run_step(state: "AppState", step_id: str) -> dict[str, Any]:
    step = next((s for s in STEPS if s["id"] == step_id), None)
    if step is None:
        raise KeyError(step_id)
    state.set_source("scenario")  # the script only exists in the demo scenario
    if step_id == "shift_start" or state.engine.t > step["t"]:
        state.restart()  # re-running an earlier beat replays the shift from the start
    if state.engine.t < step["t"]:
        await state.seek(step["t"])
    state.engine.running = False
    state.log("sim", f"Demo step: {step['title']}", actor="presenter")
    return step
