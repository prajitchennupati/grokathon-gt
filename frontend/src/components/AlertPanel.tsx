import { useState } from "react";
import { actionableAlerts, decideAlert, fmtT, type AlertView } from "../api";

interface Props {
  alerts: AlertView[];
  onFocus: (callsign: string) => void;
}

const SOURCE_LABEL: Record<string, string> = { grok: "Grok", cache: "Grok (cached)", canned: "Deterministic fallback" };

export default function AlertPanel({ alerts, onFocus }: Props) {
  const active = actionableAlerts(alerts);
  const recent = alerts.filter((a) => a.status === "resolved").slice(-3).reverse();

  return (
    <section className="rounded border border-edge">
      <div className="flex items-center justify-between border-b border-edge px-3 py-2">
        <div className="text-xs uppercase tracking-wider text-green-700">Conflict alerts</div>
        <div className="text-[10px] text-green-800">A approve · D dismiss</div>
      </div>
      {active.length === 0 && <div className="px-3 py-3 text-xs text-green-800">No conflicts predicted in the next 120 s.</div>}
      {active.map((a, i) => <AlertCard key={a.id} alert={a} top={i === 0} onFocus={onFocus} />)}
      {recent.length > 0 && (
        <div className="border-t border-edge px-3 py-2">
          {recent.map((a) => (
            <div key={a.id} className="text-[11px] text-green-800">
              {fmtT(a.resolved_t ?? 0)} resolved {a.a}/{a.b}
              {a.decision ? ` · ${a.decision}` : ""}
              {a.min_sep ? ` · closest ${a.min_sep.lateral_nm} nm / ${a.min_sep.vertical_ft} ft` : ""}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function AlertCard({ alert: a, top, onFocus }: { alert: AlertView; top: boolean; onFocus: (cs: string) => void }) {
  const [err, setErr] = useState<string | null>(null);
  const imminent = a.severity === "imminent";
  const decide = (d: "approve" | "dismiss") => decideAlert(a.id, d).then(() => setErr(null)).catch((e) => setErr(String(e.message)));
  const s = a.advisory?.suggestion;
  const showSuggestion = a.advisory_state === "ready" && a.suggestion_valid && s;

  return (
    <div className={`border-b border-edge p-3 ${a.decision ? "bg-red-950/30" : imminent ? "alert-flash" : "bg-red-950/60"}`}>
      <div className="flex items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${imminent ? "bg-red-500 text-black" : "bg-amber-500 text-black"}`}>
          {a.severity.toUpperCase()}
        </span>
        <button className="font-bold text-red-300 hover:underline" onClick={() => onFocus(a.a)}>{a.a}</button>
        <span className="text-red-400">×</span>
        <button className="font-bold text-red-300 hover:underline" onClick={() => onFocus(a.b)}>{a.b}</button>
        {top && !a.decision && <span className="ml-auto text-[10px] text-red-300">TOP</span>}
      </div>
      <div className="mt-1 text-[11px] text-red-200">
        CPA {a.geometry.t_cpa}s · {a.geometry.lateral_nm} nm · {a.geometry.vertical_ft} ft
        {a.geometry.t_los > 0 ? ` · LoS in ${a.geometry.t_los}s` : " · LOSS OF SEPARATION"}
      </div>

      {a.advisory_state === "pending" ? (
        <div className="mt-2 animate-pulse text-xs text-cyan-300">Grok is analysing the conflict…</div>
      ) : (
        <>
          {a.advisory && <div className="mt-2 text-xs text-white">{a.advisory.summary}</div>}
          {showSuggestion ? (
            <div className="mt-2 rounded border border-cyan-700 bg-black/60 p-2">
              <div className="text-[10px] uppercase tracking-wider text-cyan-600">Suggested · probe-verified</div>
              <div className="mt-1 text-sm font-bold text-cyan-200">“{s.phraseology}”</div>
              <div className="mt-1 text-[11px] text-cyan-500">{a.advisory?.rationale}</div>
            </div>
          ) : (
            <div className="mt-2 rounded border border-amber-700 bg-black/60 p-2 text-xs text-amber-300">
              No validated suggestion{a.validation_note ? ` — ${a.validation_note}` : ""}.
            </div>
          )}
          <div className="mt-1 text-[10px] text-green-800">
            {SOURCE_LABEL[a.advisory_source] ?? a.advisory_source}
            {a.advisory_error ? ` · ${a.advisory_error}` : ""}
          </div>
        </>
      )}

      {a.decision ? (
        <div className="mt-2 text-xs font-bold text-green-400">
          {a.decision === "approved" ? "✓ APPROVED — pilot complying" : "✗ DISMISSED"} at {fmtT(a.decision_t ?? 0)} · monitoring
        </div>
      ) : (
        <div className="mt-2 flex gap-2">
          <button
            disabled={!showSuggestion}
            onClick={() => decide("approve")}
            className="flex-1 rounded border border-green-500 bg-green-600/20 py-1 text-xs font-bold text-green-300 hover:bg-green-600/40 disabled:opacity-30"
          >
            Approve (A)
          </button>
          <button
            onClick={() => decide("dismiss")}
            className="flex-1 rounded border border-red-500 py-1 text-xs font-bold text-red-300 hover:bg-red-900/40"
          >
            Dismiss (D)
          </button>
        </div>
      )}
      {err && <div className="mt-1 text-[11px] text-amber-400">{err}</div>}
    </div>
  );
}
