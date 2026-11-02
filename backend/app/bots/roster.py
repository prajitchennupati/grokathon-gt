"""The four back-office Bots and their live status."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

ROLE_INFO = {
    "briefing": ("Briefing Bot", "Shift briefer — weather, NOTAMs, closures, flow"),
    "relief": ("Relief Bot", "Position relief assistant"),
    "coordination": ("Coordination Bot", "Inter-facility coordinator"),
    "paperwork": ("Paperwork Bot", "Shift log & incident reports clerk"),
}

# Controller minutes a task would otherwise take by hand. Deliberately rough and shown in the UI.
MINUTES_SAVED = {
    "briefing": 15,  # pulling METAR/TAF, NOTAMs, TMIs and writing a shift briefing
    "relief": 6,  # assembling a position relief briefing
    "coordination": 3,  # per coordination message drafted
    "shift_summary": 20,  # end-of-shift log write-up
    "incident_report": 45,  # first draft of an incident/LoS report with timeline
}


@dataclass
class BotState:
    role: str
    mode: str = "fallback"  # live (Grok Bot) | fallback (xAI API)
    working_since: Optional[float] = None
    working_reason: str = ""
    last_output_ts: Optional[float] = None
    last_output_t_sim: Optional[int] = None
    tasks_completed: int = 0
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def view(self, pending_approvals: int) -> dict[str, Any]:
        name, title = ROLE_INFO[self.role]
        status = "working" if self.working_since else "waiting_for_approval" if pending_approvals else "idle"
        return {
            "role": self.role, "name": name, "title": title, "mode": self.mode, "status": status,
            "working_since": self.working_since, "working_reason": self.working_reason,
            "last_output_ts": self.last_output_ts, "last_output_t_sim": self.last_output_t_sim,
            "tasks_completed": self.tasks_completed, "pending_approvals": pending_approvals, "note": self.note,
        }

    def start(self, reason: str) -> None:
        self.working_since, self.working_reason, self.note = time.time(), reason, ""

    def finish(self, t_sim: int) -> None:
        self.working_since, self.working_reason = None, ""
        self.last_output_ts, self.last_output_t_sim = time.time(), t_sim
        self.tasks_completed += 1


class Roster:
    def __init__(self, default_mode: str = "fallback") -> None:
        self.bots = {role: BotState(role, mode=default_mode) for role in ROLE_INFO}

    def reset(self) -> None:
        for b in self.bots.values():
            b.working_since, b.working_reason, b.note = None, "", ""
            b.last_output_ts = b.last_output_t_sim = None
            b.tasks_completed = 0
