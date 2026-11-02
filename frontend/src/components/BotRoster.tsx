import { fmtT, runBot, setBotMode, type BotView } from "../api";

const STATUS: Record<BotView["status"], { label: string; cls: string }> = {
  idle: { label: "IDLE", cls: "border-green-800 text-green-600" },
  working: { label: "WORKING", cls: "border-cyan-500 text-cyan-300 animate-pulse" },
  waiting_for_approval: { label: "WAITING FOR APPROVAL", cls: "border-amber-500 text-amber-300" },
};

const ICON: Record<string, string> = { briefing: "☀", relief: "⇄", coordination: "☏", paperwork: "✎" };

export default function BotRoster({ roster, onOpen }: { roster: BotView[]; onOpen: (role: BotView["role"]) => void }) {
  return (
    <section className="rounded border border-edge">
      <div className="border-b border-edge px-3 py-2 text-xs uppercase tracking-wider text-green-700">Bot crew</div>
      <div className="grid grid-cols-2 gap-2 p-2">
        {roster.map((b) => {
          const st = STATUS[b.status];
          return (
            <div key={b.role} className="flex flex-col gap-1 rounded border border-edge bg-black/40 p-2">
              <button className="text-left" onClick={() => onOpen(b.role)} title="Show latest output">
                <div className="text-xs font-bold text-violet-300">{ICON[b.role]} {b.name}</div>
                <div className="text-[10px] leading-tight text-green-700">{b.title}</div>
              </button>
              <span className={`self-start rounded border px-1 text-[9px] font-bold ${st.cls}`}>{st.label}</span>
              <div className="text-[10px] text-green-700">
                {b.last_output_t_sim != null ? `last ${fmtT(b.last_output_t_sim)}` : "no output yet"} · {b.tasks_completed} done
              </div>
              {b.note && <div className="text-[10px] leading-tight text-amber-500/80">{b.note}</div>}
              <div className="mt-auto flex overflow-hidden rounded border border-edge text-[9px] font-bold">
                {(["live", "fallback"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setBotMode(b.role, m)}
                    className={`flex-1 py-0.5 ${b.mode === m ? (m === "live" ? "bg-violet-600/40 text-violet-200" : "bg-green-700/40 text-green-200") : "text-green-800 hover:text-green-500"}`}
                  >
                    {m === "live" ? "Grok Bot (live)" : "Fallback (xAI)"}
                  </button>
                ))}
              </div>
              <div className="flex gap-1">
                <button onClick={() => runBot(b.role)} disabled={b.status === "working"}
                  className="flex-1 rounded border border-edge py-0.5 text-[10px] text-green-400 hover:border-target disabled:opacity-30">
                  Run now
                </button>
                {b.status === "working" && b.mode === "live" && (
                  <button onClick={() => runBot(b.role, true)}
                    className="flex-1 rounded border border-amber-700 py-0.5 text-[10px] text-amber-400 hover:bg-amber-900/30">
                    Use fallback
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
