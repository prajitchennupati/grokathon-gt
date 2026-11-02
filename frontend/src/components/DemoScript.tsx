import { useEffect, useState } from "react";
import { api, fmtT } from "../api";

interface Step { id: string; t: number; title: string; say: string }

export default function DemoScript({ t, onClose }: { t: number; onClose: () => void }) {
  const [steps, setSteps] = useState<Step[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { api<Step[]>("/api/demo/steps").then(setSteps).catch(() => {}); }, []);

  // the current step is the last one whose time has been reached
  const current = steps.reduce<string | null>((cur, s) => (t >= s.t ? s.id : cur), null);

  const go = async (id: string) => {
    setBusy(id);
    try { await api(`/api/demo/steps/${id}`, {}); } finally { setBusy(null); }
  };

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-edge bg-panel">
      <div className="flex items-center justify-between border-b border-edge px-3 py-2">
        <div className="text-xs uppercase tracking-wider text-amber-400">Demo script</div>
        <button onClick={onClose} className="text-xs text-green-700 hover:text-green-400">✕</button>
      </div>
      <ol className="flex-1 overflow-y-auto">
        {steps.map((s, i) => {
          const active = s.id === current;
          const done = current !== null && steps.findIndex((x) => x.id === current) > i;
          return (
            <li key={s.id} className={`border-b border-edge p-3 ${active ? "bg-amber-500/10" : ""}`}>
              <div className="flex items-center gap-2">
                <span className={`flex h-5 w-5 items-center justify-center rounded-full border text-[10px] font-bold ${
                  active ? "border-amber-400 text-amber-300" : done ? "border-green-700 text-green-600" : "border-edge text-green-800"}`}>
                  {done ? "✓" : i + 1}
                </span>
                <span className={`text-xs font-bold ${active ? "text-amber-200" : "text-green-300"}`}>{s.title}</span>
                <span className="ml-auto text-[10px] text-green-800">{fmtT(s.t)}</span>
              </div>
              <p className="mt-1 text-[11px] leading-snug text-green-600">{s.say}</p>
              <button
                onClick={() => go(s.id)}
                disabled={busy !== null}
                className="mt-2 w-full rounded border border-amber-600 py-0.5 text-[10px] font-bold text-amber-300 hover:bg-amber-900/30 disabled:opacity-40"
              >
                {busy === s.id ? "…" : s.id === "shift_start" ? "Start shift (restart)" : t >= s.t ? "Re-run from here" : "Jump here"}
              </button>
            </li>
          );
        })}
      </ol>
      <div className="border-t border-edge p-3 text-[10px] leading-relaxed text-green-700">
        Space pause/resume · A approve top alert · D dismiss. Or press ▶ Run at 2x/4x — auto-pause stops at each beat.
      </div>
    </aside>
  );
}
