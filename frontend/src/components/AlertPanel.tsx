import { useState } from "react";
import { decideAlert, type AlertView } from "../api";

const SOURCE_LABEL: Record<string, string> = { grok: "Grok", cache: "Grok (cached)", canned: "built-in fallback" };

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/** One conflict, reduced to what a controller needs at a glance. */
export function AlertCard({ alert: a, live, onFocus }: { alert: AlertView; live: boolean; onFocus: (cs: string) => void }) {
  const [why, setWhy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const imminent = a.severity === "imminent";
  const s = a.advisory?.suggestion;
  const ready = a.advisory_state === "ready";
  const valid = ready && a.suggestion_valid && !!s;
  const decide = (d: "approve" | "dismiss") => decideAlert(a.id, d).then(() => setErr(null)).catch((e) => setErr(String(e.message)));

  return (
    <div className={`rounded-lg border-2 p-4 ${imminent && !a.decision ? "alert-flash border-red-500" : "border-red-700 bg-red-950/50"}`}>
      <div className="flex items-center gap-2">
        <span className={`rounded px-2 py-0.5 text-xs font-bold text-black ${imminent ? "bg-red-500" : "bg-amber-400"}`}>
          {imminent ? "IMMINENT" : "CONFLICT"}
        </span>
        <button className="text-lg font-bold text-white hover:underline" onClick={() => onFocus(a.a)}>{a.a}</button>
        <span className="text-red-400">⇄</span>
        <button className="text-lg font-bold text-white hover:underline" onClick={() => onFocus(a.b)}>{a.b}</button>
      </div>
      <div className="mt-1 text-sm text-red-200">
        {a.geometry.lateral_nm} nm · {a.geometry.vertical_ft} ft apart in {mmss(a.geometry.t_cpa)}
      </div>

      {a.decision ? (
        <div className="mt-3 text-base font-bold text-green-400">
          {a.decision === "approved" ? (live ? "✓ Logged as issued" : "✓ Approved — pilot complying") : "✕ Dismissed"}
        </div>
      ) : !ready ? (
        <div className="mt-3 animate-pulse text-base text-cyan-300">Grok is thinking…</div>
      ) : valid ? (
        <>
          <div className="mt-3 text-lg font-bold leading-snug text-cyan-200">“{s!.phraseology}”</div>
          <div className="mt-3 flex gap-2">
            <button onClick={() => decide("approve")}
              className="flex-1 rounded-md bg-green-600 py-2.5 text-base font-bold text-black hover:bg-green-500">
              ✓ {live ? "Log as issued" : "Approve"} <kbd className="ml-1 text-xs opacity-60">A</kbd>
            </button>
            <button onClick={() => decide("dismiss")}
              className="rounded-md border-2 border-red-500 px-4 py-2.5 text-base font-bold text-red-300 hover:bg-red-900/50">
              ✕ <kbd className="ml-1 text-xs opacity-60">D</kbd>
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="mt-3 text-base font-bold text-amber-300">No safe single fix found — issue a traffic alert.</div>
          <button onClick={() => decide("dismiss")}
            className="mt-3 w-full rounded-md border-2 border-amber-600 py-2 text-sm font-bold text-amber-300 hover:bg-amber-900/40">
            Acknowledge <kbd className="ml-1 text-xs opacity-60">D</kbd>
          </button>
        </>
      )}

      {ready && a.advisory && (
        <button onClick={() => setWhy(!why)} className="mt-2 text-xs text-green-700 hover:text-green-400">{why ? "▾" : "▸"} Why?</button>
      )}
      {why && a.advisory && (
        <div className="mt-1 space-y-1 text-xs text-green-300/80">
          <p>{a.advisory.summary}</p>
          <p>{a.advisory.rationale}</p>
          <p className="text-green-800">
            Source: {SOURCE_LABEL[a.advisory_source] ?? a.advisory_source}. Every suggestion is checked by the conflict probe before it is shown.
            {live && " Live traffic: approving only records the decision."}
          </p>
        </div>
      )}
      {err && <div className="mt-1 text-xs text-amber-400">{err}</div>}
    </div>
  );
}
