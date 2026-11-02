"""Bot inbox contract, dropbox, approvals, relief acks, paperwork and exports."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.bots.service import checklist_items, ingest_dropbox_file
from app.config import settings
from app.models import BotPost

TOKEN = {"X-Clearance-Token": "test-token"}

VALID = {
    "role": "coordination",
    "kind": "coordination_drafts",
    "title": "Weather coordination",
    "body_markdown": "# Drafts\n- request MIT",
    "proposed_actions": [{"type": "send_message", "to": "Atlanta Center (ZTL)", "summary": "Request 10 MIT over FALCN",
                          "body": "ATL TRACON to Atlanta Center: request 10 miles in trail over FALCN due to weather."}],
    "sources": [{"title": "NAS Status", "url": "https://nasstatus.faa.gov/"}],
}


@pytest.fixture
def client(monkeypatch):
    from app import main

    main.state.restart()
    with TestClient(main.app) as c:
        yield c, main.state


# ---- schema ----------------------------------------------------------------------

def test_schema_accepts_minimal_post():
    p = BotPost.model_validate({"role": "briefing", "kind": "Shift Briefing", "title": "t", "body_markdown": "b"})
    assert p.kind == "shift_briefing" and p.proposed_actions == [] and p.sources == []


@pytest.mark.parametrize("patch", [
    {"role": "weather"},  # unknown role
    {"title": ""},
    {"body_markdown": ""},
    {"proposed_actions": [{"to": "ZTL"}]},  # action missing type/summary
    {"sources": [{"url": "https://x"}]},  # source missing title
    {"proposed_actions": "send it"},
])
def test_schema_rejects_bad_posts(patch):
    with pytest.raises(ValueError):
        BotPost.model_validate({**VALID, **patch})


# ---- webhook -----------------------------------------------------------------------

def test_inbox_requires_token(client):
    c, _ = client
    assert c.post("/api/bots/coordination/inbox", json=VALID).status_code == 401
    assert c.post("/api/bots/coordination/inbox", json=VALID, headers={"X-Clearance-Token": "nope"}).status_code == 401
    assert c.post("/api/bots/coordination/inbox", json={}).status_code == 401  # auth before schema errors


def test_inbox_rejects_role_mismatch_and_unknown_role(client):
    c, _ = client
    assert c.post("/api/bots/briefing/inbox", json=VALID, headers=TOKEN).status_code == 422
    assert c.post("/api/bots/weather/inbox", json={**VALID, "role": "weather"}, headers=TOKEN).status_code in (404, 422)


def test_inbox_post_creates_output_and_pending_approval(client):
    c, state = client
    r = c.post("/api/bots/coordination/inbox", json=VALID, headers=TOKEN)
    assert r.status_code == 201 and r.json()["approvals_created"] == 1
    snap = c.get("/api/state").json()
    out = snap["bots"]["outputs"][-1]
    assert out["via"] == "webhook" and out["role"] == "coordination"
    (appr,) = [a for a in snap["bots"]["approvals"] if a["output_id"] == out["id"]]
    assert appr["status"] == "pending"
    bot = next(b for b in snap["bots"]["roster"] if b["role"] == "coordination")
    assert bot["status"] == "waiting_for_approval"

    # nothing is "sent" until approved
    assert not any("SENT" in e["message"] for e in snap["log"])
    assert c.post(f"/api/approvals/{appr['id']}", json={"decision": "approve"}).status_code == 200
    snap = c.get("/api/state").json()
    assert any(e["message"].startswith("SENT (simulated) to Atlanta Center") for e in snap["log"])
    assert snap["restrictions"] and "10 MIT" in snap["restrictions"][0]
    # decisions are final
    assert c.post(f"/api/approvals/{appr['id']}", json={"decision": "decline"}).status_code == 404


def test_context_endpoint_requires_token_and_serves_role_context(client):
    c, _ = client
    assert c.get("/api/bots/relief/context").status_code == 401
    ctx = c.get("/api/bots/relief/context", headers=TOKEN).json()
    assert {"traffic", "active_alerts", "pending_approvals", "weather", "equipment", "restrictions_in_effect"} <= set(ctx)


# ---- dropbox -----------------------------------------------------------------------

def test_dropbox_ingests_valid_and_rejects_invalid(client, tmp_path):
    _, state = client
    good = tmp_path / "good.json"
    good.write_text(json.dumps({**VALID, "role": "briefing", "proposed_actions": []}))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"role": "briefing"}))
    assert ingest_dropbox_file(state.bots, good).via == "dropbox"
    assert ingest_dropbox_file(state.bots, bad) is None
    assert (tmp_path / "rejected" / "bad.json").exists()
    assert list((tmp_path / "processed").iterdir())


# ---- full shift via fallback runners --------------------------------------------

def _drain(state, timeout=5.0):
    import asyncio
    deadline = time.time() + timeout
    while state._tasks and time.time() < deadline:
        time.sleep(0.05)


def test_full_shift_fallback_flow(client):
    c, state = client

    def seek(t):
        c.post("/api/sim/control", json={"action": "seek", "value": t})
        _drain(state)

    seek(1)  # shift start -> briefing
    seek(93)  # conflict -> advisory
    snap = c.get("/api/state").json()
    alert = snap["alerts"][0]
    assert alert["suggestion_valid"]
    assert c.post(f"/api/alerts/{alert['id']}/decision", json={"decision": "approve"}).status_code == 200

    seek(152)  # weather -> coordination drafts
    seek(212)  # relief -> checklist
    seek(358)  # shift end -> paperwork
    snap = c.get("/api/state").json()
    kinds = [o["kind"] for o in snap["bots"]["outputs"]]
    assert kinds[:4] == ["shift_briefing", "coordination_drafts", "relief_briefing", "shift_summary"]
    assert "incident_report" in kinds  # pop-up VFR went imminent
    assert all(o["via"] == "fallback" and o["llm_source"] == "canned" for o in snap["bots"]["outputs"])

    coord = next(o for o in snap["bots"]["outputs"] if o["kind"] == "coordination_drafts")
    pending = [a for a in snap["bots"]["approvals"] if a["output_id"] == coord["id"]]
    assert pending and all(a["status"] == "pending" for a in pending)
    assert any("10 miles in trail" in a["action"]["body"] for a in pending)

    relief = next(o for o in snap["bots"]["outputs"] if o["kind"] == "relief_briefing")
    assert len(relief["checklist"]) == 7
    for i in range(len(relief["checklist"])):
        assert c.post(f"/api/bots/outputs/{relief['id']}/ack", json={"item": i}).status_code == 200
    assert c.post(f"/api/bots/outputs/{relief['id']}/ack", json={"item": 99}).status_code == 422
    snap = c.get("/api/state").json()
    assert any("position transferred" in e["message"] for e in snap["log"])

    incident = next(o for o in snap["bots"]["outputs"] if o["kind"] == "incident_report")
    assert "DAL2290" in incident["body_markdown"] and "N8734K" in incident["body_markdown"]
    assert "Separation at CPA" in incident["body_markdown"]
    md = c.get(f"/api/bots/outputs/{incident['id']}/export.md")
    assert md.status_code == 200 and "NOT FOR OPERATIONAL USE" in md.text
    pdf = c.get(f"/api/bots/outputs/{incident['id']}/export.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    m = snap["metrics"]
    assert m["alerts_raised"] == 2 and m["suggestions_approved"] == 1
    assert m["bot_tasks_completed"] == 5 and m["minutes_saved"] > 0


def test_checklist_parser():
    md = "# t\n- [ ] **A:** x\n- [x] **B:** y\n* [ ] C\nnot an item\n"
    assert len(checklist_items(md)) == 3


@pytest.mark.parametrize("role", ["briefing", "relief", "coordination", "paperwork"])
def test_grokbot_instructions_have_inbox_url_and_no_secret(client, role):
    c, _ = client
    r = c.get(f"/api/grokbot/{role}.md")
    assert r.status_code == 200
    assert f"/api/bots/{role}/inbox" in r.text and '"role": "' + role + '"' in r.text
    assert "{{CLEARANCE_TOKEN}}" in r.text and "test-token" not in r.text
