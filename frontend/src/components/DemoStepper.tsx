import { useEffect, useState } from "react";
import { api } from "../api";

interface Step { id: string; t: number; title: string; say: string }

const SHORT: Record<string, string> = {
  shift_start: "Briefing", conflict: "Conflict", weather: "Weather", relief: "Relief", popup: "Pop-up", shift_end: "Paperwork",
};

/** One button drives the whole demo. Keyboard: N. */
export default function DemoStepper({ t, nextRef, onStep }: {
  t: number;
  nextRef: React.MutableRefObject<(() => void) | null>;
  onStep: () => void;
}) {
  const [steps, setSteps] = useState<Step[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<Step[]>("/api/demo/steps").then(setSteps).catch(() => {}); }, []);

  // index of the last beat reached (-1 before the shift starts)
  const reached = steps.reduce((idx, s, i) => (t >= s.t ? i : idx), -1);
  const next = steps[reached + 1];

  const go = async (id: string) => {
    setBusy(true);
    onStep();
    try {
      await api(`/api/demo/steps/${id}`, {});
    } finally {
      setBusy(false);
    }
  };
  nextRef.current = () => { if (!busy) go(next ? next.id : steps[0].id); };

  if (!steps.length) return null;
  return (
    <div className="pointer-events-auto flex items-center gap-4 rounded-full border border-edge bg-black/85 py-2 pl-5 pr-2 shadow-lg backdrop-blur">
      <div className="flex items-center gap-1">
        {steps.map((s, i) => (
          <button key={s.id} onClick={() => go(s.id)} disabled={busy} title={s.say} className="group flex flex-col items-center px-1.5">
            <span className={`h-2.5 w-2.5 rounded-full ${i < reached ? "bg-green-600" : i === reached ? "bg-amber-400 ring-4 ring-amber-400/25" : "bg-green-900 group-hover:bg-green-700"}`} />
            <span className={`mt-1 text-[10px] ${i === reached ? "text-amber-300" : "text-green-700"}`}>{SHORT[s.id] ?? s.title}</span>
          </button>
        ))}
      </div>
      <button
        onClick={() => nextRef.current?.()}
        disabled={busy}
        className="rounded-full bg-amber-400 px-5 py-2 text-sm font-bold text-black hover:bg-amber-300 disabled:opacity-50"
      >
        {busy ? "…" : next ? `Next: ${SHORT[next.id]} ▶` : "↺ Restart demo"}
      </button>
    </div>
  );
}
