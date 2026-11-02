import type { Snapshot } from "../api";

const LABELS: Record<string, string> = {
  briefing: "shift briefing",
  relief: "relief briefing",
  coordination: "per coordination message",
  shift_summary: "shift summary",
  incident_report: "incident report draft",
};

export default function MetricsStrip({ snap }: { snap: Snapshot }) {
  const m = snap.metrics;
  const assumptions = Object.entries(snap.bots.minutes_assumptions)
    .map(([k, v]) => `${LABELS[k] ?? k}: ${v} min`)
    .join(" · ");
  const tiles = [
    ["Alerts raised", m.alerts_raised],
    ["Suggestions approved", m.suggestions_approved],
    ["Bot tasks completed", m.bot_tasks_completed],
    ["Est. controller minutes saved*", m.minutes_saved],
  ] as const;

  return (
    <div className="flex items-center gap-6 border-b border-edge bg-black px-4 py-1.5">
      {tiles.map(([label, value]) => (
        <div key={label} className="flex items-baseline gap-2">
          <span className="text-lg font-bold tabular-nums text-target">{value ?? 0}</span>
          <span className="text-[10px] uppercase tracking-wider text-green-700">{label}</span>
        </div>
      ))}
      <div className="ml-auto max-w-[45%] truncate text-[10px] text-green-800" title={assumptions}>
        *Assumed manual effort per task — {assumptions}
      </div>
    </div>
  );
}
