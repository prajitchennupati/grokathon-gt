import { runBot, setBotMode, type BotView } from "../api";

export const HELPER_INFO: Record<string, { icon: string; name: string; job: string }> = {
  briefing: { icon: "☀", name: "Briefing", job: "Weather & airport status" },
  relief: { icon: "⇄", name: "Handover", job: "Notes for the next controller" },
  coordination: { icon: "✉", name: "Coordination", job: "Messages to other control centres" },
  paperwork: { icon: "✎", name: "Paperwork", job: "Shift & incident reports" },
};

function status(b: BotView): { text: string; dot: string } {
  if (b.status === "working") return { text: "working…", dot: "bg-cyan-400 animate-pulse" };
  if (b.status === "waiting_for_approval") return { text: "needs your OK", dot: "bg-amber-400" };
  if (b.tasks_completed) return { text: "ready", dot: "bg-green-500" };
  return { text: "idle", dot: "bg-gray-600" };
}

/** The four AI helpers as a compact 2×2 grid. Click a tile to read its latest document. */
export default function BotRoster({ roster, hasOutput, onOpen, live }: {
  roster: BotView[];
  hasOutput: (role: BotView["role"]) => boolean;
  onOpen: (role: BotView["role"]) => void;
  live: boolean;
}) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {roster.map((b) => {
        const st = status(b);
        const info = HELPER_INFO[b.role];
        const has = hasOutput(b.role);
        return (
          <div key={b.role} title={info.job}
            className={`flex min-w-0 items-center gap-1.5 rounded-lg border px-2 py-2 ${has ? "border-gray-700 bg-white/5 hover:border-gray-500" : "border-gray-800"}`}>
            <button className="flex min-w-0 flex-1 items-center gap-2 text-left disabled:cursor-default" disabled={!has} onClick={() => onOpen(b.role)}>
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-violet-900/60 text-xs text-violet-200">{info.icon}</span>
              <span className="min-w-0">
                <span className="block truncate text-[13px] font-bold text-gray-100">{info.name}</span>
                <span className="flex items-center gap-1 text-[11px] text-gray-400">
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${st.dot}`} />
                  <span className="truncate">{st.text}</span>
                </span>
              </span>
            </button>
            {live && b.status !== "working" && (
              <button onClick={() => runBot(b.role)} title={`Run the ${info.name} helper now`}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-800 text-[10px] text-gray-200 hover:bg-gray-700">
                ▶
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Where each helper runs: the real Grok Bot or the built-in version. Lives in the History drawer. */
export function HelperSettings({ roster }: { roster: BotView[] }) {
  return (
    <div className="border-b border-gray-800 px-4 py-3">
      <div className="mb-2 text-xs font-bold uppercase tracking-widest text-gray-500">Helper settings</div>
      <div className="space-y-1.5">
        {roster.map((b) => (
          <div key={b.role} className="flex items-center gap-2 text-xs">
            <span className="w-28 text-gray-300">{HELPER_INFO[b.role].name}</span>
            <div className="flex overflow-hidden rounded-md border border-gray-700 font-bold">
              {(["fallback", "live"] as const).map((m) => (
                <button key={m} onClick={() => setBotMode(b.role, m)}
                  className={`px-2 py-0.5 ${b.mode === m ? "bg-violet-600 text-white" : "text-gray-500 hover:text-gray-200"}`}>
                  {m === "live" ? "Grok Bot" : "Built-in"}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
