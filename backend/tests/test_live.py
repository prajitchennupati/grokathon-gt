"""Live ADS-B parsing and the live engine (no network: fixed payloads)."""
from app.live.engine import LiveEngine, is_east_flow
from app.sim.kinematics import Aircraft
from app.live.feed import _opensky, _readsb
from app.sim.scenario import load_scenario
from tests.conftest import SCENARIO

READSB = {"ac": [
    {"hex": "a1", "flight": "DAL123  ", "t": "B739", "lat": 33.75, "lon": -84.30, "alt_baro": 7000, "gs": 250,
     "track": 225, "baro_rate": -1200, "nav_altitude_mcp": 5000, "squawk": "4512", "seen_pos": 1.0},
    {"hex": "a2", "flight": "N12345", "t": "C172", "lat": 33.70, "lon": -84.50, "alt_baro": "ground", "gs": 10, "track": 90},
    {"hex": "a3", "flight": "UAL9", "t": "B38M", "lat": 33.64, "lon": -84.43, "alt_baro": 36000, "gs": 460, "track": 90},
    {"hex": "a4", "flight": "N5526J", "t": "C172", "lat": 33.40, "lon": -84.60, "alt_baro": 3500, "gs": 100, "track": 0, "squawk": "1200"},
]}


def test_readsb_skips_ground_traffic():
    t = _readsb(READSB)
    assert [x.callsign for x in t] == ["DAL123", "UAL9", "N5526J"]
    assert t[0].selected_alt_ft == 5000 and t[0].vs_fpm == -1200


def test_opensky_parses_units():
    (t,) = _opensky({"time": 100, "states": [
        ["ab", "AAL1 ", "US", 98, 100, -84.2, 33.6, 3048.0, False, 128.6, 95.0, -5.08, None, 3100, "3475", False, 0],
        ["cd", "GND", "US", 98, 100, -84.2, 33.6, 0, True, 5, 95.0, 0, None, 0, None, False, 0],
    ]}, now=100)
    assert t.callsign == "AAL1" and round(t.alt_ft) == 10000 and round(t.gs_kt) == 250 and t.age_s == 2


def test_live_engine_filters_and_dead_reckons():
    eng = LiveEngine(load_scenario(SCENARIO))
    eng.update(_readsb(READSB), "test")
    assert set(eng.aircraft) == {"DAL123", "N5526J"}  # FL360 overflight filtered out
    assert eng.aircraft["DAL123"].tgt_alt_ft == 5000
    assert eng.aircraft["N5526J"].flight_rules == "VFR"
    x0 = eng.aircraft["DAL123"].x
    eng.tick()
    assert eng.aircraft["DAL123"].x < x0  # moving SW
    try:
        eng.apply_action("DAL123", "climb", 9000)
        assert False, "live traffic must not be controllable"
    except PermissionError:
        pass


def test_flow_from_wind():
    assert is_east_flow(100, 8) and not is_east_flow(270, 10) and not is_east_flow(100, 3)
    eng = LiveEngine(load_scenario(SCENARIO))
    eng.east_flow = True
    assert {r["id"] for r in eng.static_view()["runways"]} == {"8L", "9R", "10"}


def test_parallel_finals_detected_and_suppressed():
    from app.conflict.probe import probe
    eng = LiveEngine(load_scenario(SCENARIO))
    eng.east_flow = True  # finals west of the field, heading ~090
    rws = {rid: (thr, course) for rid, thr, course in eng.landing_runways()}
    acs = []
    for i, rid in enumerate(("8L", "9R")):
        (tx, ty), course = rws[rid]
        ac = Aircraft(callsign=f"F{i}", type="B712", x=tx - 11, y=ty, alt_ft=3800, heading=course, gs_kt=180,
                      tgt_alt_ft=3500, tgt_gs_kt=180)
        eng.aircraft[ac.callsign] = ac
        acs.append(ac)
    for ac in acs:
        rw = eng.final_for(ac)
        ac.land, ac.route = rw, [f"RW{rw}"]
    assert [a.land for a in acs] == ["8L", "9R"]
    assert probe(acs) == []


def test_light_aircraft_and_duplicates_not_probed():
    from app.live.feed import Target
    eng = LiveEngine(load_scenario(SCENARIO))
    mk = lambda hx, cs, cat, lat=33.80: Target(hx, cs, "X", lat, -84.20, 6000, 200, 90, 0, None, "4512", 0.5, cat)
    eng.update([mk("a", "N1", "A1", lat=33.90), mk("b", "DAL1", "A3"), mk("c", "DAL1", "A3", lat=33.80001)], "test")
    assert eng.aircraft["N1"].probe_exempt and not eng.aircraft["DAL1"].probe_exempt
    assert len(eng.aircraft) == 2  # duplicate DAL1 dropped
