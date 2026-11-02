"""Pre-cache every LLM response the demo uses, so `make demo OFFLINE=1` replays real Grok output.

    XAI_API_KEY=... python -m app.precache

Runs the demo steps headless against the live xAI API, approving the first conflict
suggestion as a presenter would, and writes llm/cache/. Existing entries are overwritten.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile


async def main() -> int:
    os.environ.update({"CLEARANCE_PRECACHE": "1", "CLEARANCE_OFFLINE": "0", "DEMO_MODE": "1",
                       "CLEARANCE_DB": ":memory:", "BOT_DROPBOX": tempfile.mkdtemp()})
    from .config import settings

    if not settings.llm_enabled:
        print("XAI_API_KEY and XAI_MODEL must be set (in .env) to pre-cache.", file=sys.stderr)
        return 1
    from .core import AppState
    from .demo import STEPS, run_step

    state = AppState()
    state.auto_pause = False
    for step in STEPS:
        await run_step(state, step["id"])
        if step["id"] == "conflict":
            a = state.alerts.alerts[0]
            print(f"  conflict advisory: {a.advisory_source} valid={a.suggestion_valid}")
            if a.suggestion_valid:
                state.decide_alert(a.id, "approve")
        if step["id"] == "weather":
            for ap in state.store.approvals():
                if ap.status == "pending":
                    state.bots.decide(ap.id, "approve")
        print(f"T+{state.engine.t:3d} {step['title']}")
    sources = {}
    for o in state.store.outputs():
        sources[o.kind] = o.llm_source
    for a in state.alerts.alerts:
        sources[f"advisory {a.key}"] = a.advisory_source
    print("sources:", sources)
    bad = [k for k, v in sources.items() if v != "grok"]
    if bad:
        print(f"WARNING: not from Grok (check logs): {bad}", file=sys.stderr)
    print(f"cache written to {settings.cache_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
