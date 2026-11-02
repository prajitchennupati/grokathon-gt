"""Bot orchestration: triggers, inbox ingestion, dropbox watcher, approvals.

Live mode: the app records a task and waits for the Grok Bot to post to the inbox
(webhook or dropbox). If nothing arrives within LIVE_TIMEOUT_S the fallback runner
takes over so the demo never stalls. Fallback mode runs the role through the xAI API.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from pydantic import ValidationError

from ..config import settings
from ..models import BotOutput, BotPost
from . import runners
from .roster import MINUTES_SAVED, Roster

if TYPE_CHECKING:
    from ..core import AppState

log = logging.getLogger("clearance.bots")
LIVE_TIMEOUT_S = float(os.getenv("GROKBOT_LIVE_TIMEOUT_S", "90"))
CHECKLIST_RE = re.compile(r"^\s*[-*] \[[ xX]\] ", re.M)

TRIGGERS = {"shift_start": "briefing", "weather": "coordination", "relief": "relief", "shift_end": "paperwork"}


def checklist_items(md: str) -> list[str]:
    return [line.strip() for line in md.splitlines() if CHECKLIST_RE.match(line)]


class BotService:
    def __init__(self, state: "AppState") -> None:
        self.state = state
        self.roster = Roster("fallback" if settings.demo_mode else os.getenv("GROKBOT_DEFAULT_MODE", "fallback"))
        self.minutes_saved: dict[str, int] = {}
        self._live_deadline: dict[str, float] = {}

    def reset(self) -> None:
        self.roster.reset()
        self.minutes_saved = {}
        self._live_deadline = {}

    # ---- triggers ----------------------------------------------------------
    def trigger(self, role: str, reason: str) -> None:
        bot = self.roster.bots[role]
        if bot.working_since:
            return
        bot.start(reason)
        t = self.state.engine.t
        if bot.mode == "live":
            self._live_deadline[role] = time.time() + LIVE_TIMEOUT_S
            bot.note = f"Waiting for Grok Bot (fallback in {LIVE_TIMEOUT_S:.0f}s)"
            self.state.log("bot", f"Task for {role} Grok Bot: {reason}. Waiting for inbox post.", actor=role)
            self._write_task_file(role, reason)
        else:
            self.state.log("bot", f"{role.title()} Bot started ({reason}) via xAI fallback", actor=role)
            self.state.spawn(self._run_fallback(role, t))

    async def _run_fallback(self, role: str, trigger_t: int) -> None:
        try:
            results = await runners.run(self.state, role, trigger_t)
        except Exception as e:
            log.exception("fallback runner %s failed", role)
            bot = self.roster.bots[role]
            bot.working_since, bot.note = None, f"Runner failed: {e}"
            self.state.log("bot", f"{role.title()} Bot failed: {e}", actor=role)
            await self.state.push()
            return
        for post, src, err in results:
            self.ingest(post, via="fallback", llm_source=src, llm_error=err)
        await self.state.push()

    def check_live_timeouts(self) -> None:
        now = time.time()
        for role, deadline in list(self._live_deadline.items()):
            if now >= deadline:
                del self._live_deadline[role]
                bot = self.roster.bots[role]
                bot.note = "Grok Bot timed out; ran fallback"
                self.state.log("bot", f"{role.title()} Grok Bot did not report in {LIVE_TIMEOUT_S:.0f}s; running fallback", actor=role)
                self.state.spawn(self._run_fallback(role, self.state.engine.t))

    def run_fallback_now(self, role: str) -> None:
        """Presenter override: skip waiting for the live Grok Bot."""
        self._live_deadline.pop(role, None)
        bot = self.roster.bots[role]
        if not bot.working_since:
            bot.start("manual")
        bot.note = "Fallback run requested"
        self.state.spawn(self._run_fallback(role, self.state.engine.t))

    def _write_task_file(self, role: str, reason: str) -> None:
        """For Grok Bots that watch a shared folder: a task card pointing at the context endpoint."""
        tasks = settings.dropbox_dir / "tasks"
        tasks.mkdir(parents=True, exist_ok=True)
        (tasks / f"{role}-T{self.state.engine.t}.json").write_text(json.dumps({
            "role": role, "reason": reason, "sim_t": self.state.engine.t, "created": time.time(),
            "context_url": f"{settings.public_base_url}/api/bots/{role}/context",
            "inbox_url": f"{settings.public_base_url}/api/bots/{role}/inbox",
        }, indent=2))

    # ---- ingestion -----------------------------------------------------------
    def ingest(self, post: BotPost, via: str, llm_source: str = "", llm_error: str = "") -> BotOutput:
        st = self.state
        out = BotOutput(role=post.role, kind=post.kind, title=post.title, body_markdown=post.body_markdown,
                        sources=[s.model_dump() for s in post.sources], via=via, llm_source=llm_source,
                        t_sim=st.engine.t, run_id=st.store.run_id)
        out, approvals = st.store.add_output(out, [a.model_dump() for a in post.proposed_actions])
        bot = self.roster.bots[post.role]
        self._live_deadline.pop(post.role, None)
        bot.finish(st.engine.t)
        if via != "fallback":
            bot.note = f"Received via {via}"
        elif llm_error and llm_source != "grok":
            bot.note = f"{'cached' if llm_source == 'cache' else 'template'} output ({llm_error[:80]})"
        key = post.kind if post.kind in MINUTES_SAVED else post.role
        mins = MINUTES_SAVED.get(key, 0) * (max(1, len(approvals)) if post.role == "coordination" else 1)
        self.minutes_saved[key] = self.minutes_saved.get(key, 0) + mins
        src = f"{via}" + (f"/{llm_source}" if llm_source else "")
        st.log("bot", f"{post.title} ({src})" + (f" — {len(approvals)} item(s) for approval" if approvals else ""),
               actor=post.role, output_id=out.id)
        return out

    # ---- approvals + relief acks ---------------------------------------------
    def decide(self, approval_id: int, decision: str) -> Any:
        st = self.state
        status = {"approve": "approved", "decline": "declined"}[decision]
        a = st.store.decide(approval_id, status, st.engine.t, time.time())
        if a is None:
            raise KeyError("no pending approval with that id")
        act = a.action
        if status == "approved":
            if act.get("type") == "send_message":
                st.log("coordination", f"SENT (simulated) to {act.get('to')}: {act.get('body') or act.get('summary')}",
                       actor="controller", approval_id=a.id)
                if a.role == "coordination":
                    st.restrictions.append(f"{act.get('summary')} (coordinated T+{st.engine.t}s)")
            elif act.get("type") == "file_report":
                st.log("approval", f"FILED (simulated) to {act.get('to')}: {act.get('summary')}", actor="controller", approval_id=a.id)
            else:
                st.log("approval", f"APPROVED {a.role}: {act.get('summary')}", actor="controller", approval_id=a.id)
        else:
            st.log("approval", f"DECLINED {a.role}: {act.get('summary')}", actor="controller", approval_id=a.id)
        return a

    def ack(self, output_id: int, item: int) -> BotOutput:
        st = self.state
        out = st.store.output(output_id)
        if out is None or out.run_id != st.store.run_id:
            raise KeyError("no such output")
        items = checklist_items(out.body_markdown)
        if not 0 <= item < len(items):
            raise ValueError("no such checklist item")
        if item not in out.acked:
            out.acked = sorted([*out.acked, item])
            st.store.save_output(out)
            label = re.sub(r"^\s*[-*] \[[ xX]\]\s*", "", items[item])
            st.log("relief", f"Incoming controller acknowledged: {label[:120]}", actor="controller", output_id=out.id, item=item)
            if len(out.acked) == len(items):
                st.log("relief", "Relief briefing complete — position transferred", actor="controller", output_id=out.id)
        return out

    # ---- view ----------------------------------------------------------------
    def view(self) -> dict[str, Any]:
        st = self.state
        approvals = st.store.approvals()
        pending_by_role: dict[str, int] = {}
        for a in approvals:
            if a.status == "pending":
                pending_by_role[a.role] = pending_by_role.get(a.role, 0) + 1
        outputs = st.store.outputs()
        return {
            "roster": [b.view(pending_by_role.get(r, 0)) for r, b in self.roster.bots.items()],
            "outputs": [{**o.model_dump(), "checklist": checklist_items(o.body_markdown)} for o in outputs],
            "approvals": [a.model_dump() for a in approvals],
            "minutes_saved": self.minutes_saved,
            "minutes_assumptions": MINUTES_SAVED,
            "live_timeout_s": LIVE_TIMEOUT_S,
        }


# ---------------------------------------------------------------------------
# dropbox watcher
# ---------------------------------------------------------------------------


def ingest_dropbox_file(service: BotService, path: Path) -> Optional[BotOutput]:
    root = path.parent
    try:
        post = BotPost.model_validate_json(path.read_text())
    except (ValidationError, ValueError, OSError) as e:
        (root / "rejected").mkdir(exist_ok=True)
        shutil.move(str(path), root / "rejected" / path.name)
        (root / "rejected" / f"{path.name}.error.txt").write_text(str(e))
        service.state.log("bot", f"Rejected dropbox file {path.name}: invalid BotPost", actor="system")
        return None
    out = service.ingest(post, via="dropbox")
    (root / "processed").mkdir(exist_ok=True)
    shutil.move(str(path), root / "processed" / f"{int(time.time())}-{path.name}")
    return out


async def watch_dropbox(service: BotService, interval_s: float = 2.0) -> None:
    folder = settings.dropbox_dir
    folder.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            changed = False
            for p in sorted(folder.glob("*.json")):
                ingest_dropbox_file(service, p)
                changed = True
            if changed:
                await service.state.push()
        except Exception:
            log.exception("dropbox scan failed")
        await asyncio.sleep(interval_s)
