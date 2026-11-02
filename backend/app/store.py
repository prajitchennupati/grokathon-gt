"""SQLite persistence. Every sim restart starts a new run; queries read the current run."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func
from sqlmodel import Session, SQLModel, create_engine, select

from .models import Approval, BotOutput, LogEntry


class Store:
    def __init__(self, path: Path | str) -> None:
        url = "sqlite://" if str(path) == ":memory:" else f"sqlite:///{path}"
        self.db = create_engine(url, connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self.db)
        with Session(self.db) as s:
            last = s.exec(select(func.max(LogEntry.run_id))).one()
        self.run_id = (last or 0) + 1

    def new_run(self) -> None:
        self.run_id += 1

    # ---- log -------------------------------------------------------------
    def log(self, t_sim: int, kind: str, message: str, actor: str = "system", **data: Any) -> LogEntry:
        entry = LogEntry(run_id=self.run_id, t_sim=t_sim, kind=kind, actor=actor, message=message, data=data)
        with Session(self.db, expire_on_commit=False) as s:
            s.add(entry)
            s.commit()
        return entry

    def logs(self, limit: Optional[int] = None) -> list[LogEntry]:
        with Session(self.db) as s:
            q = select(LogEntry).where(LogEntry.run_id == self.run_id).order_by(LogEntry.id.desc())
            if limit:
                q = q.limit(limit)
            return list(reversed(s.exec(q).all()))

    # ---- bot outputs + approvals ----------------------------------------
    def add_output(self, out: BotOutput, actions: list[dict[str, Any]]) -> tuple[BotOutput, list[Approval]]:
        out.run_id = self.run_id
        with Session(self.db, expire_on_commit=False) as s:
            s.add(out)
            s.commit()
            s.refresh(out)
            approvals = [Approval(run_id=self.run_id, output_id=out.id, role=out.role, action=a, t_sim=out.t_sim) for a in actions]
            for a in approvals:
                s.add(a)
            s.commit()
            for a in approvals:
                s.refresh(a)
        return out, approvals

    def outputs(self, role: Optional[str] = None) -> list[BotOutput]:
        with Session(self.db) as s:
            q = select(BotOutput).where(BotOutput.run_id == self.run_id)
            if role:
                q = q.where(BotOutput.role == role)
            return list(s.exec(q.order_by(BotOutput.id)).all())

    def output(self, output_id: int) -> Optional[BotOutput]:
        with Session(self.db) as s:
            return s.get(BotOutput, output_id)

    def save_output(self, out: BotOutput) -> None:
        with Session(self.db, expire_on_commit=False) as s:
            s.merge(out)
            s.commit()

    def approvals(self) -> list[Approval]:
        with Session(self.db) as s:
            return list(s.exec(select(Approval).where(Approval.run_id == self.run_id).order_by(Approval.id)).all())

    def decide(self, approval_id: int, status: str, t_sim: int, ts: float) -> Optional[Approval]:
        with Session(self.db, expire_on_commit=False) as s:
            a = s.get(Approval, approval_id)
            if a is None or a.run_id != self.run_id or a.status != "pending":
                return None
            a.status, a.decided_t_sim, a.decided_ts = status, t_sim, ts
            s.add(a)
            s.commit()
            s.refresh(a)
            return a
