"""Fallback runners: the same four Bot roles, run through the xAI API from local data.

Each runner builds the role's context, asks Grok for a BotDraft (title, markdown,
proposed actions), and falls back to a deterministic template if Grok is slow,
unavailable or returns something invalid. Outputs use the same BotPost shape a
live Grok Bot posts to the inbox.
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from ..llm.client import structured
from ..models import BotDraft, BotPost, ProposedAction, Source
from . import context as ctx

if TYPE_CHECKING:
    from ..core import AppState

COMMON = """You are a back-office assistant Bot for an FAA TRACON (Atlanta, A80). You never act on your
own: anything that would be sent or filed goes in proposed_actions for the controller to approve.
Write concise, operational Markdown a controller can scan in seconds. Use only facts in the input;
never invent aircraft, times or numbers. Respond with JSON only."""

PROMPTS = {
    "briefing": COMMON + """
Task: a one-page start-of-shift briefing. Sections (## headings): Active runways & flow, Weather & trends
(quote the METAR and summarise the TAF), Closures & NOTAMs, Equipment, Flow restrictions (TMIs), Items to watch.
proposed_actions: [] (a briefing proposes nothing).""",
    "relief": COMMON + """
Task: a position relief briefing for the incoming controller, formatted as a checklist they acknowledge
item by item. Every item MUST be a Markdown task line starting with "- [ ] " followed by a bold label, e.g.
"- [ ] **Traffic:** 11 aircraft ...". Keep every item under 20 words: decode the METAR (wind, visibility),
list only abnormal equipment, group notable aircraft by reason. Cover, in order: Weather, Runways & flow, Equipment, Restrictions in effect,
Traffic (count + notable aircraft: vectors, VFR, weather-affected, low fuel/requests if any),
Active conflicts/alerts, Pending approvals/requests. Nothing outside the checklist except one # title line.
proposed_actions: [].""",
    "coordination": COMMON + """
Task: weather has developed in the TRACON. Draft coordination messages to adjacent facilities.
Each message is one proposed_action with type "send_message", "to" = facility name, "summary" = one line
(e.g. "Request 10 MIT for ATL arrivals over FALCN"), "body" = the message text in standard interfacility
style, e.g. "ATL TRACON to Atlanta Center: request 10 miles in trail for arrivals over the west fix due to
weather." Draft 1-3 messages. body_markdown summarises the situation, affected arrivals and the drafts.""",
    "paperwork_summary": COMMON + """
Task: the end-of-shift log summary. Sections: Overview (traffic handled, runways, weather), Timeline of
significant events (table: time | event), Conflicts & resolutions, Coordination & restrictions,
Bot assistance, Open items for next shift. proposed_actions: [].""",
    "paperwork_incident": COMMON + """
Task: a DRAFT incident report for an imminent conflict / possible loss of separation. Sections:
Summary, Aircraft involved (table: callsign | type | rules | altitude), Separation at CPA (closest observed
lateral nm and vertical ft, plus predicted CPA), Timeline (table: time | event, from the alert timeline and log),
Actions taken, Contributing factors (only if supported by the data; else "To be determined"),
Controller statement (leave a placeholder). Mark the report "DRAFT — requires controller review".
proposed_actions: exactly one, type "file_report", to "Front-line manager", summary "File incident report draft".""",
}


def _md_list(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) or "- None"


# ---------------------------------------------------------------------------
# canned templates
# ---------------------------------------------------------------------------


def canned_briefing(c: dict[str, Any]) -> BotDraft:
    b = c["inputs"]
    rw = b["active_runways"]
    abnormal = [e for e in b["equipment"] if re.search(r"out of service|U/S|OTS|inop", e, re.I)]
    watch = []
    if b["weather_outlook"]:
        watch.append("Convection west of the field after 1800Z: expect deviations and MIT over FALCN.")
    if b["runway_closures"]:
        watch += ["Crane 1.4 nm NE of the 26R approach end, 1,160 ft MSL (lit).",
                  "TWY E closed between D and F: longer taxi-in for 27L arrivals."]
    if b["taf"]:
        watch.append("Watch the forecast for wind shifts that would flip the runway flow.")
    sections = [
        f"# {b['airport']} shift briefing",
        f"## Runways\n**{b['flow']}** — landing **{' / '.join(rw['arrivals'])}**, departing **{' / '.join(rw['departures'])}**",
        "## Weather\n" + "\n".join(filter(None, [
            f"- Now: **{_metar_brief(b['metar'])}** — `{b['metar']}`",
            f"- Forecast: `{b['taf']}`" if b["taf"] else "",
            _md_list(b["weather_outlook"][:1]) if b["weather_outlook"] else "",
        ])),
    ]
    if b["runway_closures"]:
        sections.append("## Closures\n" + _md_list(b["runway_closures"]))
    if b["equipment"]:
        sections.append("## Equipment\n" + (_md_list(abnormal) if abnormal else "- All normal"))
    if b["traffic_management"][2:]:
        sections.append("## Flow restrictions\n" + _md_list(b["traffic_management"][2:]))
    if watch:
        sections.append("## Watch this shift\n" + _md_list(watch))
    return BotDraft(title=f"{b['airport']} shift briefing", body_markdown="\n\n".join(sections) + "\n")


def _metar_brief(metar: str) -> str:
    """'KATL 021452Z 27009KT 10SM ...' -> 'wind 270 at 9 kt, vis 10 SM'."""
    import re

    wind = re.search(r"\b(\d{3}|VRB)(\d{2,3})(G\d{2,3})?KT\b", metar)
    vis = re.search(r"\b(\d{1,2}|P6)SM\b", metar)
    parts = []
    if wind:
        parts.append(f"wind {wind.group(1)} at {int(wind.group(2))} kt" + (f" gusting {wind.group(3)[1:]}" if wind.group(3) else ""))
    if vis:
        parts.append(f"vis {vis.group(1).replace('P6', '6+')} SM")
    return ", ".join(parts) or metar


def canned_relief(c: dict[str, Any]) -> BotDraft:
    tr = c["traffic"]
    groups: dict[str, list[str]] = {}
    for a in tr:
        if any(a["callsign"] in w["arrivals_routed_through_affected_fix"] for w in c["weather"]["cells"]):
            groups.setdefault("routed into weather", []).append(a["callsign"])
        elif a["rules"] == "VFR":
            groups.setdefault("VFR", []).append(a["callsign"])
        elif a["on_vector"]:
            groups.setdefault("on vectors", []).append(a["callsign"])
    watch = "; ".join(f"{', '.join(cs)} ({why})" for why, cs in groups.items())
    cells = "; ".join(f"{w['intensity']} cell {w['center']}" for w in c["weather"]["cells"])
    abnormal = [e for e in c["equipment"] if re.search(r"out of service|U/S|OTS|inop", e, re.I)]
    coordinated = [r for r in c["restrictions_in_effect"] if "coordinated" in r]
    alerts = c["active_alerts"]
    alert_txt = "; ".join("/".join(a["pair"]) + f" ({a['max_severity']})" for a in alerts) or "none"
    n_pend = len(c["pending_approvals"])
    rw = c["active_runways"]
    body = f"""# Relief briefing — {c['sim_time']}

- [ ] **Weather:** {_metar_brief(c['weather']['metar'])}{f'; {cells}' if cells else ''}.
- [ ] **Runways:** landing {' / '.join(rw['arrivals'])}, departing {' / '.join(rw['departures'])}.
{f"- [ ] **Equipment:** {'; '.join(abnormal) if abnormal else 'all normal'}.{chr(10)}" if c['equipment'] else ''}- [ ] **Restrictions:** {'; '.join(r.split(' (coordinated')[0] for r in coordinated) if coordinated else 'none coordinated'}.
- [ ] **Traffic:** {len(tr)} aircraft.{f' Watch: {watch}.' if watch else ''}
- [ ] **Conflicts:** {alert_txt}.
- [ ] **Pending:** {f'{n_pend} item(s) awaiting your approval' if n_pend else 'nothing'}.
"""
    return BotDraft(title="Relief briefing", body_markdown=body)


def canned_coordination(c: dict[str, Any]) -> BotDraft:
    actions: list[ProposedAction] = []
    lines = []
    for w in c["weather_cells"]:
        fix = w["affects_fix"] or "the west gate"
        affected = w["arrivals_routed_through_affected_fix"]
        lines.append(f"- **{w['intensity'].title()} cell** {w['center']}, moving {w['moving']}, over **{fix}**. "
                     f"Arrivals routed via {fix}: {', '.join(affected) or 'none on scope'}.")
        actions.append(ProposedAction(
            type="send_message", to="Atlanta Center (ZTL)", summary=f"Request 10 MIT for ATL arrivals over {fix}",
            body=f"ATL TRACON to Atlanta Center: request 10 miles in trail for ATL arrivals over {fix} due to weather, "
                 f"effective immediately until further advised."))
        if affected:
            actions.append(ProposedAction(
                type="send_message", to="Atlanta Center (ZTL)", summary=f"Request reroute of {fix} arrivals north of the cell",
                body=f"ATL TRACON to Atlanta Center: request arrivals filed over {fix} be routed north of the weather to CHERO; "
                     f"{', '.join(affected)} already in the TRACON will be vectored."))
        actions.append(ProposedAction(
            type="send_message", to="Atlanta Tower (ATL)", summary="Advise Tower of weather and arrival deviations",
            body=f"ATL TRACON to Atlanta Tower: {w['intensity']} precipitation {w['center']} moving {w['moving']}; "
                 f"expect west-gate arrivals deviating north, possible gaps on final."))
    if not actions:
        lines.append("- No weather cells on the scope; no coordination required.")
    body = "# Weather coordination drafts\n\n## Situation\n" + "\n".join(lines) + \
           "\n\n## Drafts\nEach message is waiting for your approval."
    return BotDraft(title="Weather coordination drafts", body_markdown=body, proposed_actions=actions)


def canned_summary(c: dict[str, Any]) -> BotDraft:
    log = c["shift_log"]
    significant = [e for e in log if e["kind"] in ("event", "alert", "approval", "coordination", "relief", "instruction", "bot")]
    rows = "\n".join(f"| {e['t']} | {e['message'].replace('|', '/')} |" for e in significant) or "| — | No significant events |"
    alerts = c["alerts"]
    conflicts = "\n".join(
        f"- **{'/'.join(a['pair'])}** ({a['max_severity']}) detected {a['detected']}, "
        f"{'resolved ' + a['resolved'] if a['resolved'] else 'still active'}; "
        f"decision: {a['decision'] or 'none'}"
        + (f"; closest {a['closest_observed']['lateral_nm']} nm / {a['closest_observed']['vertical_ft']} ft" if a["closest_observed"] else "")
        for a in alerts) or "- None"
    m = c["metrics"]
    body = f"""# End-of-shift summary — {c['position']}

## Overview
- Facility: {c['facility']}, airport {c['airport']}, west flow.
- Arrivals landed this session: {len(c['landed'])} ({', '.join(l['callsign'] + ' ' + str(l['runway']) for l in c['landed']) or 'none'}).
- Conflict alerts: {m.get('alerts_raised', 0)}; suggestions approved {m.get('suggestions_approved', 0)}, dismissed {m.get('suggestions_dismissed', 0)}.

## Timeline of significant events
| Time | Event |
|---|---|
{rows}

## Conflicts & resolutions
{conflicts}

## Coordination & restrictions
{_md_list(c['restrictions_in_effect'])}

## Open items for next shift
- Monitor convection west of the field; review west-gate MIT with ZTL.
- Review any draft incident reports before filing.
"""
    return BotDraft(title="End-of-shift summary", body_markdown=body)


def canned_incident(c: dict[str, Any], alert: dict[str, Any], specs: dict[str, Any]) -> BotDraft:
    a_cs, b_cs = alert["pair"]
    rows_ac = "\n".join(
        f"| {cs} | {specs.get(cs, {}).get('type', '?')} | {specs.get(cs, {}).get('flight_rules', '?')} | "
        f"{(alert['closest_observed'] or {}).get('alt_a' if cs == a_cs else 'alt_b', '?')} ft |" for cs in (a_cs, b_cs))
    timeline = "\n".join(
        f"| T+{ev['t']}s | {ev['event']}"
        + (f" (pred. {ev['lateral_nm']} nm / {ev['vertical_ft']} ft in {ev['t_cpa']} s)" if "t_cpa" in ev else "") + " |"
        for ev in alert["timeline"])
    for e in c["shift_log"]:
        if e["kind"] in ("advisory", "approval") and (a_cs in e["message"] or b_cs in e["message"]):
            t = int(e["t"].strip("T+s"))
            if alert["timeline"] and alert["timeline"][0]["t"] <= t <= (alert["timeline"][-1]["t"] or t):
                timeline += f"\n| {e['t']} | {e['message'].replace('|', '/')} |"
    co = alert["closest_observed"] or {}
    first = alert["timeline"][0] if alert["timeline"] else {}
    actions = []
    if alert["decision"] == "approved" and alert["suggestion"]:
        actions.append(f"Controller approved advisory: “{alert['suggestion']}”")
    elif alert["decision"] == "dismissed":
        actions.append("Controller dismissed the advisory; separation handled by controller.")
    else:
        actions.append("No validated single-aircraft resolution was available; controller action not recorded in the log.")
    body = f"""# Incident report — {a_cs} / {b_cs}

**DRAFT — for controller review.**

## Summary
{alert['max_severity'].title()} conflict between {a_cs} and {b_cs} detected {alert['detected']} at {c['facility']}, {c['position']}.
Closest observed separation {co.get('lateral_nm', '?')} nm lateral / {co.get('vertical_ft', '?')} ft vertical at T+{co.get('t', '?')}s.

## Aircraft involved
| Callsign | Type | Rules | Altitude at CPA |
|---|---|---|---|
{rows_ac}

## Separation at CPA
- Closest observed: **{co.get('lateral_nm', '?')} nm / {co.get('vertical_ft', '?')} ft** at T+{co.get('t', '?')}s
- Predicted at detection: {first.get('lateral_nm', '?')} nm / {first.get('vertical_ft', '?')} ft in {first.get('t_cpa', '?')} s
- Minima: 3 nm lateral / 1,000 ft vertical

## Timeline
| Time | Event |
|---|---|
{timeline}

## Actions taken
{_md_list(actions)}

## Contributing factors
- To be determined.

## Controller statement
_[To be completed by the controller.]_
"""
    return BotDraft(
        title=f"Incident report draft — {a_cs}/{b_cs}", body_markdown=body,
        proposed_actions=[ProposedAction(type="file_report", to="Front-line manager", summary="File incident report draft",
                                         body=f"Draft incident report for {a_cs}/{b_cs} attached for review.")])


# ---------------------------------------------------------------------------
# runners
# ---------------------------------------------------------------------------


async def _draft(state: "AppState", prompt_key: str, kind_key: str, c: dict[str, Any], canned: BotDraft) -> tuple[BotDraft, str, str]:
    r = await structured(
        task=f"bot_{prompt_key}",
        cache_key=f"{state.engine.scenario.name}:{kind_key}",
        system=PROMPTS[prompt_key],
        user=json.dumps(c, indent=1, default=str),
        schema=BotDraft,
        canned=lambda: canned,
    )
    return r.value, r.source, r.error


def _post(role: str, kind: str, d: BotDraft, sources: list[Source] | None = None) -> BotPost:
    return BotPost(role=role, kind=kind, title=d.title, body_markdown=d.body_markdown,
                   proposed_actions=d.proposed_actions, sources=sources or [])


async def run(state: "AppState", role: str, trigger_t: int) -> list[tuple[BotPost, str, str]]:
    """Returns [(post, llm_source, llm_error)]."""
    c = ctx.for_role(state, role)
    if role == "briefing":
        d, src, err = await _draft(state, "briefing", f"briefing:t{trigger_t}", c, canned_briefing(c))
        srcs = [Source(**s) for s in c["inputs"]["sources"]]
        return [(_post(role, "shift_briefing", d, srcs), src, err)]
    if role == "relief":
        d, src, err = await _draft(state, "relief", f"relief:t{trigger_t}", c, canned_relief(c))
        return [(_post(role, "relief_briefing", d), src, err)]
    if role == "coordination":
        d, src, err = await _draft(state, "coordination", f"coordination:t{trigger_t}", c, canned_coordination(c))
        return [(_post(role, "coordination_drafts", d), src, err)]
    if role == "paperwork":
        d, src, err = await _draft(state, "paperwork_summary", f"summary:t{trigger_t}", c, canned_summary(c))
        out = [(_post(role, "shift_summary", d), src, err)]
        specs = {s.callsign: s.model_dump() for s in state.engine.scenario.aircraft}
        for alert in c["alerts"]:
            if alert["max_severity"] != "imminent":
                continue
            ic = {**c, "incident": alert, "aircraft": {cs: specs.get(cs) for cs in alert["pair"]}}
            d, src, err = await _draft(state, "paperwork_incident", f"incident:{'|'.join(alert['pair'])}:t{trigger_t}",
                                       ic, canned_incident(c, alert, specs))
            out.append((_post(role, "incident_report", d), src, err))
        return out
    raise KeyError(role)
