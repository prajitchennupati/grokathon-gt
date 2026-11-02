import { runBot, setBotMode, type BotView } from "../api";

const INFO: Record<string, { icon: string; name: string; job: string }> = {
  briefing: { icon: "☀", name: "Briefing", job: "Weather & airport status" },
  relief: { icon: "⇄", name: "Handover", job: "Notes for the next controller" },
  coordination: { icon: "✉", name: "Coordination", job: "Messages to other control centres" },
  paperwork: { icon: "✎", name: "Paperwork", job: "Shift & incident reports" },
};

function status(b: BotView): { text: string; cls: string } {
  if (b.status === "working") return { text: "working…", cls: "text-cyan-300 animate-pulse" };
  if (b.status === "waiting_for_approval") return { text: "needs your OK", cls: "text-amber-300" };
  if (b.tasks_completed) return { text: "done ✓", cls: "text-green-400" };
  return { text: "waiting", cls: "text-gray-500" };
}

/** The four AI helpers, one row each. Click to read what they wrote. */
export default function BotRoster({ roster, hasOutput, onOpen }: {
  roster: BotView[];
  hasOutput: (role: BotView["role"]) => boolean;
  onOpen: (role: BotView["role"]) => void;
}) {
  return (
    <div className="space-y-1">
      {roster.map((b) => {
        const st = status(b);
        const info = INFO[b.role];
        const has = hasOutput(b.role);
        return (
          <div key={b.role} className="group flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-white/5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-violet-900/60 text-violet-200">{info.icon}</span>
            <button className="min-w-0 flex-1 text-left disabled:cursor-default" disabled={!has} onClick={() => onOpen(b.role)}>
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-bold text-gray-100">{info.name}</span>
                <span className={`text-xs ${st.cls}`}>{st.text}</span>
              </div>
              <div className="truncate text-[11px] text-gray-500">{info.job}</div>
            </button>
            {has && <button onClick={() => onOpen(b.role)} className="text-xs font-bold text-cyan-400 hover:underline">Read</button>}
            <button onClick={() => runBot(b.role)} disabled={b.status === "working"} title="Run this helper now"
              className="hidden rounded border border-gray-700 px-1.5 text-[10px] text-gray-400 hover:text-white group-hover:block disabled:opacity-30">
              run
            </button>
            <button
              onClick={() => setBotMode(b.role, b.mode === "live" ? "fallback" : "live")}
              title={b.mode === "live" ? "Using the real Grok Bot. Click to use the built-in version." : "Using the built-in version (xAI API). Click to use the real Grok Bot."}
              className={`hidden rounded px-1.5 text-[10px] font-bold group-hover:block ${b.mode === "live" ? "bg-violet-600/60 text-violet-100" : "bg-gray-800 text-gray-400"}`}
            >
              {b.mode === "live" ? "GROK BOT" : "BUILT-IN"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
