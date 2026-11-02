import os
import sys
import tempfile
from pathlib import Path

import pytest

# isolate the app from the developer's .env / database before anything imports settings
os.environ.update({
    "CLEARANCE_DB": ":memory:", "BOT_DROPBOX": tempfile.mkdtemp(prefix="clearance-dropbox-"),
    "CLEARANCE_TOKEN": "test-token", "XAI_API_KEY": "", "CLEARANCE_OFFLINE": "1", "DEMO_MODE": "0",
})

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sim.engine import SimEngine  # noqa: E402
from app.sim.scenario import load_scenario  # noqa: E402

SCENARIO = Path(__file__).resolve().parents[1] / "scenarios" / "atl_arrivals_demo.json"


@pytest.fixture
def engine() -> SimEngine:
    return SimEngine(load_scenario(SCENARIO))
