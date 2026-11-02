import { runBot, setBotMode, type BotView } from "../api";

const ICON: Record<string, string> = { briefing: "☀", relief: "⇄", coordination: "☏", paperwork: "✎" };
const SHORT: Record<string, string> = { briefing: "Briefing", relief: "Relief", coordination: "Coordination", paperwork: "Paperwork" };

function status(b: BotView): { text: string; cls: string } {
  if (b.status === "working") return { text: "working…", cls: "text-cyan-300 animate-pulse" };
  if (b.status === "waiting_for_approval") return { text: "needs you", cls: "text-amber-300" };
  if (b.tasks_completed) return { text: "done", cls: "text-green-500" };
  return { text: "standing by", cls: "text-green-800" };
}

/** Four one-line rows. Click a Bot to read its latest document. */
export default function BotRoster({ roster, hasOutput, onOpen }: {
  roster: BotView[];
  hasOutput: (role: BotView["role"]) => boolean;
  onOpen: (role: BotView["role"]) => void;
}) {
  return (
    <div className="space-y-1">
      {roster.map((b) => {
        const st = status(b);
        return (
          <div key={b.role} className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-green-950/50">
            <button className="flex flex-1 items-center gap-2 text-left disabled:cursor-default" disabled={!hasOutput(b.role)} onClick={() => onOpen(b.role)}>
              <span className="w-5 text-center text-violet-300">{ICON[b.role]}</span>
              <span className="text-sm font-bold text-green-100">{SHORT[b.role]}</span>
              <span className={`text-xs ${st.cls}`}>{st.text}</span>
              {hasOutput(b.role) && <span className="ml-auto text-xs text-cyan-500 group-hover:underline">open</span>}
            </button>
            <button
              onClick={() => runBot(b.role)}
              disabled={b.status === "working"}
              title="Run this Bot now"
              className="hidden rounded border border-edge px-1.5 text-[10px] text-green-500 hover:border-target group-hover:block disabled:opacity-30"
            >
              run
            </button>
            <button
              onClick={() => setBotMode(b.role, b.mode === "live" ? "fallback" : "live")}
              title={b.mode === "live" ? "Using the real Grok Bot (click for xAI API fallback)" : "Using the xAI API fallback (click to use the real Grok Bot)"}
              className={`rounded px-1.5 text-[10px] font-bold ${b.mode === "live" ? "bg-violet-600/50 text-violet-100" : "bg-green-900/60 text-green-400"}`}
            >
              {b.mode === "live" ? "GROK BOT" : "API"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
