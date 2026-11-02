import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sim.engine import SimEngine  # noqa: E402
from app.sim.scenario import load_scenario  # noqa: E402

SCENARIO = Path(__file__).resolve().parents[1] / "scenarios" / "atl_arrivals_demo.json"


@pytest.fixture
def engine() -> SimEngine:
    return SimEngine(load_scenario(SCENARIO))
