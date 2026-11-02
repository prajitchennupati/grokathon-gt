import math

import pytest

from app.conflict.alerts import AlertManager, validated_candidates
from app.conflict.probe import Maneuver, cpa, probe, probe_pair, validate_maneuver
from app.sim.kinematics import Aircraft


def mk(cs, x, y, hdg, gs=300, alt=8000, tgt_alt=None, **kw) -> Aircraft:
    return Aircraft(callsign=cs, type="B738", x=x, y=y, alt_ft=alt, heading=hdg, gs_kt=gs,
                    tgt_alt_ft=alt if tgt_alt is None else tgt_alt, tgt_gs_kt=gs, **kw)


# ---- analytic CPA ------------------------------------------------------------

def test_cpa_head_on():
    t, d = cpa((0, 0), (0.1, 0), (10, 0), (-0.1, 0))
    assert math.isclose(t, 50) and math.isclose(d, 0, abs_tol=1e-9)


def test_cpa_diverging_is_now():
    t, d = cpa((0, 0), (-0.1, 0), (5, 0), (0.1, 0))
    assert t == 0 and math.isclose(d, 5)


def test_cpa_parallel_same_speed():
    t, d = cpa((0, 0), (0.1, 0), (0, 4), (0.1, 0))
    assert t == 0 and math.isclose(d, 4)


# ---- probe -------------------------------------------------------------------

def test_head_on_same_altitude_is_conflict():
    # 600 kt closure, 10 nm apart -> CPA at 60 s
    c = probe_pair(mk("A1", 0, 0, 90), mk("B1", 10, 0, 270))
    assert c is not None
    assert c.t_cpa == 60 and c.lateral_nm < 0.01 and c.severity == "predicted"
    assert c.t_los == 42  # 3 nm apart after 42 s at 0.1667 nm/s closure


def test_head_on_close_is_imminent():
    c = probe_pair(mk("A1", 0, 0, 90), mk("B1", 6, 0, 270))
    assert c is not None and c.severity == "imminent" and c.t_cpa == 36


def test_crossing_conflict():
    # both reach the origin at t=60
    c = probe_pair(mk("A1", -5, 0, 90), mk("B1", 0, -5, 0))
    assert c is not None and c.t_cpa == 60 and c.lateral_nm < 0.01


def test_crossing_with_miss_distance_beyond_3nm_is_clear():
    # B passes 60 s behind A
    assert probe_pair(mk("A1", -5, 0, 90), mk("B1", 0, -10, 0)) is None


def test_overtaking_conflict():
    # B 3.5 nm behind A, 150 kt faster -> closes 0.5 nm in 12 s, keeps closing
    c = probe_pair(mk("A1", 3.5, 0, 90, gs=200), mk("B1", 0, 0, 90, gs=350))
    assert c is not None and c.t_los == 12 and c.t_cpa == 84


def test_diverging_is_clear():
    assert probe_pair(mk("A1", 0, 0, 270), mk("B1", 3.5, 0, 90)) is None


def test_vertically_separated_is_clear():
    assert probe_pair(mk("A1", 0, 0, 90, alt=8000), mk("B1", 10, 0, 270, alt=9000)) is None


def test_999_ft_is_conflict_1000_is_not():
    assert probe_pair(mk("A1", 0, 0, 90, alt=8000), mk("B1", 10, 0, 270, alt=8999)) is not None
    assert probe_pair(mk("A1", 0, 0, 90, alt=8000), mk("B1", 10, 0, 270, alt=9000)) is None


def test_descent_into_conflict_uses_assigned_altitude():
    # B is at 10,000 descending to 8,000: separated now, not at CPA
    c = probe_pair(mk("A1", 0, 0, 90, alt=8000), mk("B1", 10, 0, 270, alt=10000, tgt_alt=8000))
    assert c is not None


def test_level_off_prevents_false_alert():
    # B descending but levels at 9,000
    assert probe_pair(mk("A1", 0, 0, 90, alt=8000), mk("B1", 10, 0, 270, alt=10000, tgt_alt=9000)) is None


def test_beyond_lookahead_is_clear():
    # CPA at 150 s
    assert probe_pair(mk("A1", 0, 0, 90), mk("B1", 25, 0, 270)) is None


def test_parallel_finals_to_different_runways_suppressed():
    a = mk("A1", 14, 0.8, 270, gs=180, alt=5500, route=["RW26R"], land="26R")
    b = mk("B1", 14, -0.3, 270, gs=180, alt=5500, route=["RW27L"], land="27L")
    assert probe([a, b]) == []
    b.land, b.route = "26R", ["RW26R"]  # same runway: not suppressed
    assert len(probe([a, b])) == 1


# ---- suggestion validation -----------------------------------------------------

@pytest.fixture
def head_on():
    return {"A1": mk("A1", 0, 0, 90), "B1": mk("B1", 10, 0, 270)}


def test_climb_1000_resolves(head_on):
    ok, note = validate_maneuver(head_on.values(), "A1|B1", Maneuver("A1", "climb", 9000))
    assert ok, note


def test_small_climb_does_not_resolve(head_on):
    ok, note = validate_maneuver(head_on.values(), "A1|B1", Maneuver("A1", "climb", 8500))
    assert not ok and "does not resolve" in note


def test_turn_resolves(head_on):
    ok, _ = validate_maneuver(head_on.values(), "A1|B1", Maneuver("A1", "turn", 45))
    assert ok


def test_suggestion_creating_new_conflict_rejected(head_on):
    head_on["C1"] = mk("C1", 5, 0, 0, gs=0.0, alt=9000)  # parked at 9,000 near the CPA
    ok, note = validate_maneuver(head_on.values(), "A1|B1", Maneuver("A1", "climb", 9000))
    assert not ok and "C1" in note


def test_suggestion_for_uninvolved_aircraft_rejected(head_on):
    head_on["C1"] = mk("C1", 30, 30, 0)
    ok, note = validate_maneuver(head_on.values(), "A1|B1", Maneuver("C1", "climb", 12000))
    assert not ok


def test_unknown_callsign_rejected(head_on):
    ok, _ = validate_maneuver(head_on.values(), "A1|B1", Maneuver("ZZZ", "climb", 9000))
    assert not ok


def test_candidates_are_all_valid_and_cheapest_first(head_on):
    cands = validated_candidates(head_on, "A1|B1")
    assert cands and cands[0].action in ("climb", "descend")
    for m in cands:
        assert validate_maneuver(head_on.values(), "A1|B1", m)[0]


# ---- alert lifecycle ------------------------------------------------------------

def test_alert_lifecycle_new_escalate_resolve():
    acs = {"A1": mk("A1", 0, 0, 90), "B1": mk("B1", 15, 0, 270)}
    mgr = AlertManager()
    new, _, _ = mgr.update(acs, 0)
    assert len(new) == 1 and new[0].severity == "predicted"
    acs["A1"].x, acs["B1"].x = 2, 10  # 8 nm apart -> CPA in 48 s
    new, esc, _ = mgr.update(acs, 1)
    assert not new and len(esc) == 1 and mgr.alerts[0].max_severity == "imminent"
    acs["B1"].alt_ft = acs["B1"].tgt_alt_ft = 10000
    for t in range(2, 2 + 3):
        _, _, res = mgr.update(acs, t)
    assert res and mgr.alerts[0].status == "resolved"
    assert mgr.alerts[0].min_sep["lateral_nm"] == 8


def test_terminal_area_low_traffic_suppressed():
    # two departures side by side off parallel runways, 4 nm out at 3,000 ft
    a = mk("A1", -4, 0.8, 270, gs=200, alt=3000)
    b = mk("B1", -4, -0.3, 270, gs=200, alt=3000)
    assert probe([a, b]) == []
    a.alt_ft = a.tgt_alt_ft = b.alt_ft = b.tgt_alt_ft = 6000  # above the suppression ceiling
    assert len(probe([a, b])) == 1
