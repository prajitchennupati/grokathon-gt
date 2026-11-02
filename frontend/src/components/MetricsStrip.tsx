import type { Snapshot } from "../api";

const LABELS: Record<string, string> = {
  briefing: "shift briefing",
  relief: "relief briefing",
  coordination: "per coordination message",
  shift_summary: "shift summary",
  incident_report: "incident report draft",
};

export function minutesAssumptions(snap: Snapshot): string {
  return Object.entries(snap.bots.minutes_assumptions).map(([k, v]) => `${LABELS[k] ?? k}: ${v} min`).join(" · ");
}

/** The four session numbers, with the minutes-saved assumptions spelled out. */
export default function MetricsStrip({ snap }: { snap: Snapshot }) {
  const m = snap.metrics;
  const tiles = [
    ["Alerts", m.alerts_raised],
    ["Approved", m.suggestions_approved],
    ["Bot tasks", m.bot_tasks_completed],
    ["Minutes saved*", m.minutes_saved],
  ] as const;
  return (
    <div className="border-b border-edge px-4 py-3">
      <div className="grid grid-cols-4 gap-2">
        {tiles.map(([label, value]) => (
          <div key={label} className="rounded border border-edge p-2 text-center">
            <div className="text-2xl font-bold tabular-nums text-target">{value ?? 0}</div>
            <div className="text-[10px] uppercase tracking-wider text-green-700">{label}</div>
          </div>
        ))}
      </div>
      <div className="mt-2 text-[10px] leading-snug text-green-800">*Assumed manual effort per task — {minutesAssumptions(snap)}</div>
    </div>
  );
}
