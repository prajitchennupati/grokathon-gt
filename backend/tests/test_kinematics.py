import math

from app.sim.geo import LocalProjection, bearing, heading_diff
from app.sim.kinematics import Aircraft, step


def mk(**kw) -> Aircraft:
    base = dict(callsign="T1", type="B738", x=0.0, y=0.0, alt_ft=8000, heading=90, gs_kt=360, tgt_alt_ft=8000, tgt_gs_kt=360)
    base.update(kw)
    return Aircraft(**base)


def test_straight_and_level_moves_gs_per_second():
    ac = mk()
    for _ in range(10):
        step(ac, {})
    assert math.isclose(ac.x, 1.0, abs_tol=1e-9)  # 360 kt = 0.1 nm/s
    assert math.isclose(ac.y, 0.0, abs_tol=1e-9)
    assert ac.alt_ft == 8000


def test_standard_rate_turn_on_vector():
    ac = mk(tgt_heading=180)
    for _ in range(10):
        step(ac, {})
    assert math.isclose(ac.heading, 120.0)  # 3 deg/s
    for _ in range(30):
        step(ac, {})
    assert math.isclose(ac.heading, 180.0)


def test_forced_turn_direction_goes_long_way():
    ac = mk(heading=90, tgt_heading=60, turn_dir="right")
    step(ac, {})
    assert math.isclose(ac.heading, 93.0)


def test_climb_and_descent_rates():
    ac = mk(tgt_alt_ft=9000)
    for _ in range(60):
        step(ac, {})
    assert ac.alt_ft == 9000  # 1500 fpm for 40 s, then level
    ac.tgt_alt_ft = 7000
    for _ in range(30):
        step(ac, {})
    assert math.isclose(ac.alt_ft, 8000)  # 2000 fpm
    assert math.isclose(ac.vs_fpm, -2000)


def test_speed_change_rate():
    ac = mk(tgt_gs_kt=300)
    for _ in range(20):
        step(ac, {})
    assert math.isclose(ac.gs_kt, 330)


def test_route_following_captures_fix_and_advances():
    fixes = {"A": (0.0, 5.0), "B": (5.0, 5.0)}
    ac = mk(heading=0, route=["A", "B"])
    for _ in range(80):
        step(ac, fixes)
    assert ac.route_idx == 1
    assert abs(heading_diff(bearing(ac.x, ac.y, 5, 5), ac.heading)) < 5


def test_landing_on_glidepath_removes_at_threshold():
    fixes = {"RW": (0.0, 0.0)}
    ac = mk(x=8.0, heading=270, alt_ft=3600, tgt_alt_ft=4000, gs_kt=180, tgt_gs_kt=180, route=["RW"], land="RW")
    for t in range(400):
        step(ac, fixes, runway_elev_ft=1000)
        if ac.landed:
            break
    assert ac.landed
    assert ac.alt_ft < 1300


def test_projection_roundtrip():
    p = LocalProjection(33.6367, -84.4281)
    x, y = p.to_xy(33.7, -84.3)
    lat, lon = p.to_latlon(x, y)
    assert math.isclose(lat, 33.7) and math.isclose(lon, -84.3)
    assert math.isclose(y, 0.0633 * 60, rel_tol=1e-3)
