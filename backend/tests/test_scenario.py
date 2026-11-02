"""The demo scenario's scripted beats must fire on schedule."""
from app.conflict.probe import probe


def test_about_twelve_aircraft_with_expected_operators(engine):
    specs = engine.scenario.aircraft
    assert 12 <= len(specs) <= 13
    prefixes = {s.callsign[:3] for s in specs}
    assert {"DAL", "SWA", "AAL", "UAL"} <= prefixes
    assert any(s.callsign.startswith("N") for s in specs)


def test_events_fire_on_schedule(engine):
    fired = {e.kind: e.t for e in engine.fired}
    fired.update({e.kind: e.t for e in engine.run_until(engine.scenario.duration_s)})
    assert fired["shift_start"] == 0
    assert fired["weather"] == 150
    assert fired["relief"] == 210
    assert fired["shift_end"] >= 300


def test_weather_cell_is_west_of_field(engine):
    engine.run_until(150)
    assert len(engine.weather) == 1
    xs = [x for x, _ in engine.weather[0].polygon_xy]
    assert max(xs) < 0


def test_scripted_conflicts_fire_on_schedule_and_nothing_else(engine):
    first: dict[str, tuple[int, str]] = {}
    while not engine.finished:
        engine.tick()
        for c in probe(engine.aircraft.values()):
            first.setdefault(c.key, (engine.t, c.severity))
    assert list(first) == ["DAL1423|SWA2210", "DAL2290|N8734K"]
    t, sev = first["DAL1423|SWA2210"]
    assert 80 <= t <= 100 and sev == "predicted"
    t, sev = first["DAL2290|N8734K"]
    assert t == 240 and sev == "imminent"


def test_replay_is_deterministic(engine):
    engine.run_until(180)
    a = engine.snapshot()["aircraft"]
    engine.reset()
    engine.run_until(180)
    assert engine.snapshot()["aircraft"] == a
