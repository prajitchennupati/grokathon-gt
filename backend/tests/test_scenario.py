"""The demo scenario's scripted beats must fire on schedule."""
from app.conflict.probe import probe


def test_twelve_aircraft_with_expected_operators(engine):
    specs = engine.scenario.aircraft
    assert len(specs) == 12
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


def test_scripted_conflict_appears_near_t90_and_is_the_only_one(engine):
    first: dict[str, int] = {}
    while engine.t < 200:
        engine.tick()
        for c in probe(engine.aircraft.values()):
            first.setdefault(c.key, engine.t)
    assert list(first) == ["DAL1423|SWA2210"]
    assert 80 <= first["DAL1423|SWA2210"] <= 100


def test_replay_is_deterministic(engine):
    engine.run_until(180)
    a = engine.snapshot()["aircraft"]
    engine.reset()
    engine.run_until(180)
    assert engine.snapshot()["aircraft"] == a
