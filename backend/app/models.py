"""Pydantic schemas (LLM + inbox contracts) and SQLModel tables."""
from __future__ import annotations

import time
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField

# ---------------------------------------------------------------------------
# LLM output schemas
# ---------------------------------------------------------------------------


class Suggestion(BaseModel):
    callsign: str
    action: Literal["climb", "descend", "turn", "speed"]
    value: float
    phraseology: str


class ConflictAdvisory(BaseModel):
    summary: str
    suggestion: Suggestion
    rationale: str


# ---------------------------------------------------------------------------
# Bot inbox contract (Grok Bot webhook / dropbox / fallback runners)
# ---------------------------------------------------------------------------

BotRole = Literal["briefing", "relief", "coordination", "paperwork"]
ROLES: tuple[str, ...] = ("briefing", "relief", "coordination", "paperwork")


class ProposedAction(BaseModel):
    type: str = Field(description="send_message | file_report | apply_restriction | other")
    summary: str
    to: Optional[str] = None
    body: str = ""


class Source(BaseModel):
    title: str
    url: str = ""


class BotPost(BaseModel):
    role: BotRole
    kind: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    body_markdown: str = Field(min_length=1, max_length=50_000)
    proposed_actions: list[ProposedAction] = Field(default_factory=list, max_length=20)
    sources: list[Source] = Field(default_factory=list, max_length=50)

    @field_validator("kind")
    @classmethod
    def _kind_slug(cls, v: str) -> str:
        return v.strip().lower().replace(" ", "_")


class BotDraft(BaseModel):
    """What a fallback runner asks the LLM for; role/kind are filled in by the app."""

    title: str
    body_markdown: str
    proposed_actions: list[ProposedAction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def _now() -> float:
    return time.time()


class LogEntry(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    run_id: int = SQLField(index=True)
    t_sim: int
    ts: float = SQLField(default_factory=_now)
    kind: str  # alert | approval | bot | sim | relief | coordination | ...
    actor: str = "system"  # controller | system | <bot role>
    message: str
    data: dict[str, Any] = SQLField(default_factory=dict, sa_column=Column(JSON))


class BotOutput(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    run_id: int = SQLField(index=True)
    role: str = SQLField(index=True)
    kind: str
    title: str
    body_markdown: str
    sources: list[dict[str, Any]] = SQLField(default_factory=list, sa_column=Column(JSON))
    via: str  # webhook | dropbox | fallback
    llm_source: str = ""  # grok | cache | canned (fallback runner only)
    t_sim: int = 0
    ts: float = SQLField(default_factory=_now)
    acked: list[int] = SQLField(default_factory=list, sa_column=Column(JSON))  # relief checklist items


class Approval(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    run_id: int = SQLField(index=True)
    output_id: int = SQLField(index=True)
    role: str
    action: dict[str, Any] = SQLField(default_factory=dict, sa_column=Column(JSON))
    status: str = "pending"  # pending | approved | declined
    t_sim: int = 0
    ts: float = SQLField(default_factory=_now)
    decided_ts: Optional[float] = None
    decided_t_sim: Optional[int] = None
