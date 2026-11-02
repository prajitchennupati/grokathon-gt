import asyncio
import json

import pytest

from app.config import settings
from app.conflict.alerts import AlertManager
from app.llm import client, phraseology
from app.llm.advisory import advise
from app.models import ConflictAdvisory
from app.sim.kinematics import Aircraft


def mk(cs, x, hdg):
    return Aircraft(callsign=cs, type="B738", x=x, y=0, alt_ft=8000, heading=hdg, gs_kt=300, tgt_alt_ft=8000, tgt_gs_kt=300)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cache_dir", tmp_path)
    monkeypatch.setattr(settings, "xai_api_key", "")
    monkeypatch.setattr(settings, "offline", True)


@pytest.mark.parametrize("cs,spoken", [
    ("DAL1423", "Delta fourteen twenty-three"),
    ("SWA2210", "Southwest twenty-two ten"),
    ("UAL455", "United four fifty-five"),
    ("DAL1200", "Delta twelve hundred"),
    ("N172SP", "November one seven two sierra papa"),
])
def test_callsign_telephony(cs, spoken):
    assert phraseology.callsign(cs) == spoken


def test_altitude_and_heading_phraseology():
    assert phraseology.instruction("DAL1423", "climb", 10000) == "Delta fourteen twenty-three, climb and maintain one zero thousand."
    assert phraseology.altitude(9500) == "niner thousand five hundred"
    assert phraseology.altitude(23000) == "flight level two three zero"
    assert phraseology.instruction("SWA2210", "turn", 90, current_heading=170) == "Southwest twenty-two ten, turn left heading zero niner zero."


def _alert():
    acs = {"A1": mk("A1", 0, 90), "B1": mk("B1", 15, 270)}
    new, _, _ = AlertManager().update(acs, 0)
    return new[0], acs


def test_offline_without_cache_uses_validated_canned_advisory():
    alert, acs = _alert()
    result, ok, note = asyncio.run(advise(alert, acs, "unit"))
    assert result.source == "canned" and ok, note
    assert result.value.suggestion.callsign in ("A1", "B1")


def test_cache_hit_is_used_and_still_validated():
    alert, acs = _alert()
    bad = ConflictAdvisory.model_validate({
        "summary": "cached", "rationale": "r",
        "suggestion": {"callsign": "A1", "action": "climb", "value": 8200, "phraseology": "x"},
    })
    p = client.cache_path("conflict_advisory", f"unit:{alert.key}:t0")
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"response": bad.model_dump()}))
    result, ok, note = asyncio.run(advise(alert, acs, "unit"))
    assert result.source == "cache" and result.value.summary == "cached"
    assert not ok and "does not resolve" in note  # cached/LLM output never bypasses the probe


def test_live_call_failure_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "offline", False)
    monkeypatch.setattr(settings, "xai_api_key", "k")
    monkeypatch.setattr(settings, "xai_model", "m")
    monkeypatch.setattr(settings, "llm_timeout_s", 0.05)

    async def slow(*a, **k):
        await asyncio.sleep(1)

    monkeypatch.setattr(client, "_call_grok", slow)
    alert, acs = _alert()
    result, ok, _ = asyncio.run(advise(alert, acs, "unit"))
    assert result.source == "canned" and "timeout" in result.error and ok


def test_strict_schema_requires_all_fields():
    s = client._strict_schema(ConflictAdvisory)
    assert s["additionalProperties"] is False and set(s["required"]) == {"summary", "suggestion", "rationale"}
