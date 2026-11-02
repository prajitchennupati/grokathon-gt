import { useState } from "react";
import { decideAlert, type AlertView } from "../api";
import { flightName, mmss, plainSuggestion } from "../friendly";

const SOURCE_LABEL: Record<string, string> = { grok: "Grok", cache: "Grok", canned: "Clearance's built-in logic" };

/** One conflict in everyday language: what's happening, the fix, and two buttons. */
export function AlertCard({ alert: a, live, onFocus }: { alert: AlertView; live: boolean; onFocus: (cs: string) => void }) {
  const [why, setWhy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const urgent = a.severity === "imminent";
  const s = a.advisory?.suggestion;
  const ready = a.advisory_state === "ready";
  const valid = ready && a.suggestion_valid && !!s;
  const g = a.geometry;
  const decide = (d: "approve" | "dismiss") => decideAlert(a.id, d).then(() => setErr(null)).catch((e) => setErr(String(e.message)));

  return (
    <div className={`rounded-xl border-2 p-4 ${urgent && !a.decision ? "alert-flash border-red-500" : "border-red-600 bg-red-950/60"}`}>
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-red-300">
        <span className={`h-2.5 w-2.5 rounded-full ${urgent ? "bg-red-500" : "bg-amber-400"}`} />
        {urgent ? "Urgent: planes too close" : "Planes getting too close"}
      </div>
      <div className="mt-2 text-base font-bold leading-snug text-white">
        <button className="underline decoration-dotted underline-offset-4 hover:text-cyan-300" onClick={() => onFocus(a.a)}>{flightName(a.a)}</button>
        {" and "}
        <button className="underline decoration-dotted underline-offset-4 hover:text-cyan-300" onClick={() => onFocus(a.b)}>{flightName(a.b)}</button>
      </div>
      <div className="mt-1 text-sm text-red-100">
        {g.t_cpa > 0 ? <>In <b>{mmss(g.t_cpa)}</b> they'll be </> : <>They are </>}
        <b>{g.lateral_nm} nautical miles</b> apart with <b>{Math.round(g.vertical_ft).toLocaleString()} ft</b> of height between them.
        <span className="text-red-300/80"> They need 3 miles or 1,000 ft.</span>
      </div>

      {a.decision ? (
        <div className="mt-3 rounded-lg bg-green-900/50 p-2 text-sm font-bold text-green-300">
          {a.decision === "approved" ? (live ? "✓ Logged" : "✓ Approved — the pilot is following the fix") : "Dismissed"}
        </div>
      ) : !ready ? (
        <div className="mt-3 animate-pulse text-sm text-cyan-300">Working out a safe fix…</div>
      ) : valid ? (
        <>
          <div className="mt-3 rounded-lg bg-black/50 p-3">
            <div className="text-[11px] font-bold uppercase tracking-wider text-cyan-400">Suggested fix · safety-checked</div>
            <div className="mt-1 text-base font-bold text-cyan-100">{plainSuggestion(s!)}</div>
            <div className="mt-1 text-xs italic text-cyan-300/70">Radio call: “{s!.phraseology}”</div>
          </div>
          <div className="mt-3 flex gap-2">
            <button onClick={() => decide("approve")} className="flex-1 rounded-lg bg-green-500 py-3 text-base font-bold text-black hover:bg-green-400">
              ✓ {live ? "Log it" : "Approve fix"}
            </button>
            <button onClick={() => decide("dismiss")} className="rounded-lg border-2 border-red-400 px-4 py-3 text-sm font-bold text-red-200 hover:bg-red-900/60">
              Ignore
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="mt-3 rounded-lg bg-black/50 p-3 text-sm text-amber-200">
            <b>No safe automatic fix.</b> Every option the system checked would still be too close, so it won't guess.
            The controller warns both pilots directly.
          </div>
          <button onClick={() => decide("dismiss")} className="mt-3 w-full rounded-lg border-2 border-amber-500 py-2.5 text-sm font-bold text-amber-200 hover:bg-amber-900/40">
            Got it
          </button>
        </>
      )}

      {ready && a.advisory && (
        <button onClick={() => setWhy(!why)} className="mt-2 text-xs text-red-300/70 hover:text-white">{why ? "▾" : "▸"} How was this decided?</button>
      )}
      {why && a.advisory && (
        <div className="mt-1 space-y-1 text-xs text-red-100/80">
          <p>{a.advisory.summary}</p>
          <p>{a.advisory.rationale}</p>
          <p className="text-red-300/60">
            The fix came from {SOURCE_LABEL[a.advisory_source] ?? a.advisory_source}. A separate, rule-based checker re-tests it
            against every nearby plane before it's shown. Nothing happens until a person approves it.
          </p>
        </div>
      )}
      {err && <div className="mt-1 text-xs text-amber-300">{err}</div>}
    </div>
  );
}
