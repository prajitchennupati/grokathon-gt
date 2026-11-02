import { useEffect, useState } from "react";
import { api } from "../api";

export interface Step { id: string; t: number; title: string; say: string; caption: string }

const SHORT: Record<string, string> = {
  shift_start: "Start", conflict: "Close call", weather: "Storm", relief: "Handover", popup: "Surprise", shift_end: "Reports",
};

/** One button drives the whole demo (keyboard: N). Reports the current beat for the caption. */
export default function DemoStepper({ t, nextRef, onStep, onCaption }: {
  t: number;
  nextRef: React.MutableRefObject<(() => void) | null>;
  onStep: () => void;
  onCaption: (caption: string | null) => void;
}) {
  const [steps, setSteps] = useState<Step[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<Step[]>("/api/demo/steps").then(setSteps).catch(() => {}); }, []);

  const reached = steps.reduce((idx, s, i) => (t >= s.t ? i : idx), -1);
  const next = steps[reached + 1];
  useEffect(() => { onCaption(reached >= 0 ? steps[reached].caption : null); }, [reached, steps.length]);

  const go = async (id: string) => {
    setBusy(true);
    onStep();
    try {
      await api(`/api/demo/steps/${id}`, {});
    } finally {
      setBusy(false);
    }
  };
  nextRef.current = () => { if (!busy && steps.length) go(next ? next.id : steps[0].id); };

  if (!steps.length) return null;
  return (
    <div className="pointer-events-auto flex items-center gap-3 rounded-2xl border border-gray-700 bg-black/85 py-2 pl-4 pr-2 shadow-xl backdrop-blur">
      <div className="flex items-center gap-0.5">
        {steps.map((s, i) => (
          <button key={s.id} onClick={() => go(s.id)} disabled={busy} title={s.caption} className="group flex flex-col items-center px-1.5">
            <span className={`h-3 w-3 rounded-full ${i < reached ? "bg-green-500" : i === reached ? "bg-amber-400 ring-4 ring-amber-400/30" : "bg-gray-700 group-hover:bg-gray-500"}`} />
            <span className={`mt-1 text-[10px] ${i === reached ? "font-bold text-amber-300" : "text-gray-500"}`}>{SHORT[s.id] ?? s.title}</span>
          </button>
        ))}
      </div>
      <button onClick={() => nextRef.current?.()} disabled={busy}
        className="rounded-xl bg-amber-400 px-5 py-2.5 text-sm font-bold text-black hover:bg-amber-300 disabled:opacity-50">
        {busy ? "…" : next ? (reached < 0 ? "▶ Start demo" : `Next: ${SHORT[next.id]} ▶`) : "↺ Start over"}
      </button>
    </div>
  );
}
