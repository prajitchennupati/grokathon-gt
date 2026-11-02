import { useEffect, useRef, useState } from "react";
import Scope from "./components/Scope";
import { AlertCard } from "./components/AlertPanel";
import { ApprovalCard } from "./components/ApprovalQueue";
import BotRoster from "./components/BotRoster";
import BriefingView from "./components/BriefingView";
import ShiftLog from "./components/ShiftLog";
import MetricsStrip, { minutesAssumptions } from "./components/MetricsStrip";
import DemoStepper from "./components/DemoStepper";
import { actionableAlerts, decideAlert, fmtT, setSource, simControl, useScenario, useSnapshot, type Snapshot } from "./api";

type Drawer = null | "doc" | "log";

export default function App() {
  const { snap, connected } = useSnapshot();
  const live = snap?.source === "live";
  const scenario = useScenario(`${snap?.source ?? ""}:${snap?.sim.live?.flow ?? ""}`);
  const [selected, setSelected] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [outputId, setOutputId] = useState<number | null>(null);
  const nextStep = useRef<(() => void) | null>(null);
  const sim = snap?.sim;
  const outputs = snap?.bots.outputs ?? [];

  // pop each new Bot document open as it arrives, unless it's only approval items
  // (those already show as cards on the right)
  const seenOutputs = useRef(0);
  useEffect(() => {
    if (outputs.length > seenOutputs.current) {
      const fresh = outputs.slice(seenOutputs.current).filter((o) => o.kind !== "coordination_drafts");
      if (fresh.length) {
        setOutputId(fresh[fresh.length - 1].id);
        setDrawer("doc");
      }
    }
    seenOutputs.current = outputs.length;
  }, [outputs.length]);

  // a new conflict takes priority over any open document: clear the radar
  const activeAlertIds = (snap?.alerts ?? []).filter((a) => a.status === "active").map((a) => a.id);
  const newestAlert = activeAlertIds.length ? Math.max(...activeAlertIds) : 0;
  useEffect(() => {
    if (newestAlert) setDrawer(null);
  }, [newestAlert]);

  // keyboard: Space pause · A approve · D dismiss · N next demo step · Esc close
  const snapRef = useRef<Snapshot | null>(null);
  snapRef.current = snap;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.metaKey || e.ctrlKey || e.altKey) return;
      const top = actionableAlerts(snapRef.current?.alerts ?? []).find((a) => !a.decision);
      if (e.code === "Space") { e.preventDefault(); simControl("toggle"); }
      else if (e.key === "a" || e.key === "A") { if (top?.suggestion_valid) decideAlert(top.id, "approve").catch(() => {}); }
      else if (e.key === "d" || e.key === "D") { if (top) decideAlert(top.id, "dismiss").catch(() => {}); }
      else if (e.key === "n" || e.key === "N") nextStep.current?.();
      else if (e.key === "Escape") setDrawer(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // decided alerts linger a few seconds so the presenter sees the outcome, then leave
  const alerts = actionableAlerts(snap?.alerts ?? []).filter((a) => !a.decision || (sim && a.decision_t !== null && sim.t - a.decision_t < 8));
  const approvals = (snap?.bots.approvals ?? []).filter((a) => a.status === "pending");
  const conflictCallsigns = (snap?.alerts ?? []).filter((a) => a.status === "active").flatMap((a) => [a.a, a.b]);
  const sel = sim?.aircraft.find((a) => a.callsign === selected);
  const openRole = (role: string) => {
    const o = [...outputs].reverse().find((x) => x.role === role);
    if (o) { setOutputId(o.id); setDrawer("doc"); }
  };

  return (
    <div className="flex h-full flex-col bg-black text-sm">
      {/* ---------------------------------------------------------------- header */}
      <header className="flex items-center gap-4 border-b border-edge bg-panel px-4 py-2">
        <div className="text-lg font-bold tracking-[0.2em] text-target">CLEARANCE</div>

        <div className="flex overflow-hidden rounded-md border border-edge text-xs font-bold">
          {(["scenario", "live"] as const).map((src) => (
            <button key={src} onClick={() => setSource(src)}
              className={`px-3 py-1.5 ${snap?.source === src ? (src === "live" ? "bg-red-600 text-white" : "bg-target text-black") : "text-green-600 hover:text-green-300"}`}>
              {src === "live" ? "● LIVE ATL" : "DEMO"}
            </button>
          ))}
        </div>

        {sim && (
          <div className="flex items-center gap-2">
            {!live && (
              <button onClick={() => simControl(sim.running ? "pause" : "resume")}
                className="flex h-8 w-8 items-center justify-center rounded-full bg-green-900 text-target hover:bg-green-800" title="Space">
                {sim.running ? "❚❚" : "▶"}
              </button>
            )}
            <span className="text-xl font-bold tabular-nums text-target">{live ? new Date().toUTCString().slice(17, 22) + "Z" : fmtT(sim.t)}</span>
          </div>
        )}

        {snap && snap.metrics.minutes_saved > 0 && (
          <div className="text-xs text-green-500" title={`Assumed manual effort — ${minutesAssumptions(snap)}`}>
            ⏱ <b className="text-target">{snap.metrics.minutes_saved}</b> min saved
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          <button onClick={() => setDrawer(drawer === "log" ? null : "log")} className="text-xs text-green-600 hover:text-green-300">Log</button>
          <span className="rounded border border-amber-600/70 px-2 py-0.5 text-[10px] font-bold tracking-wider text-amber-400">
            ADVISORY PROTOTYPE — NOT FOR OPERATIONAL USE
          </span>
          {!connected && <span className="text-xs text-red-500">○ reconnecting</span>}
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* ---------------------------------------------------------------- scope */}
        <main className="relative min-w-0 flex-1">
          {scenario && sim ? (
            <Scope scenario={scenario} sim={sim} selected={selected} onSelect={setSelected} conflicts={conflictCallsigns} />
          ) : (
            <div className="p-8 text-green-700">Connecting…</div>
          )}

          {/* top-left: what am I looking at */}
          {sim && (
            <div className="pointer-events-none absolute left-3 top-3 space-y-2">
              <div className="rounded bg-black/70 px-2 py-1 text-xs text-green-500">
                {live
                  ? <>Real traffic · {sim.aircraft.length} aircraft · {sim.live?.flow} flow · {sim.live?.provider || "connecting…"}{sim.live?.error && <span className="text-amber-400"> · feed error, showing last picture</span>}</>
                  : <>Demo scenario · {sim.aircraft.length} aircraft · west flow</>}
              </div>
              {sel && (
                <div className="pointer-events-auto w-56 rounded border border-select/50 bg-black/85 p-2 text-xs">
                  <div className="flex items-center">
                    <span className="text-base font-bold text-select">{sel.callsign}</span>
                    <span className="ml-2 text-green-600">{sel.type}</span>
                    <button onClick={() => setSelected(null)} className="ml-auto text-green-700 hover:text-white">✕</button>
                  </div>
                  <div className="mt-1 grid grid-cols-2 gap-x-2 text-green-200">
                    <span>{sel.alt_ft.toLocaleString()} ft</span><span>{sel.gs_kt} kt</span>
                    <span>hdg {String(Math.round(sel.heading)).padStart(3, "0")}°</span>
                    <span>{sel.vs_fpm > 300 ? "climbing" : sel.vs_fpm < -300 ? "descending" : "level"}</span>
                    {sel.land && <span className="col-span-2 text-green-500">on final {sel.land}</span>}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* bottom-center: one-button demo */}
          {sim && !live && (
            <div className="pointer-events-none absolute bottom-4 left-4 z-20">
              <DemoStepper t={sim.t} nextRef={nextStep} onStep={() => setDrawer(null)} />
            </div>
          )}

          {/* slide-over drawers */}
          {drawer && snap && (
            <div className="absolute inset-y-0 right-0 z-10 w-[min(520px,85%)] border-l border-edge bg-panel shadow-2xl">
              {drawer === "doc" && outputs.length > 0 ? (
                <BriefingView outputs={outputs} selectedId={outputId} onSelect={setOutputId} onClose={() => setDrawer(null)} />
              ) : (
                <div className="flex h-full flex-col">
                  <div className="flex items-center border-b border-edge px-4 py-2">
                    <span className="text-sm font-bold text-green-300">Shift log</span>
                    <button onClick={() => setDrawer(null)} className="ml-auto text-lg text-green-600 hover:text-white">✕</button>
                  </div>
                  <MetricsStrip snap={snap} />
                  <div className="min-h-0 flex-1"><ShiftLog log={snap.log} /></div>
                </div>
              )}
            </div>
          )}
        </main>

        {/* ---------------------------------------------------------------- right: only what needs you */}
        <aside className="flex w-[380px] shrink-0 flex-col border-l border-edge bg-panel">
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
            <div className="text-xs font-bold uppercase tracking-widest text-green-700">Needs you</div>
            {alerts.map((a) => <AlertCard key={a.id} alert={a} live={live} onFocus={setSelected} />)}
            {approvals.map((a) => <ApprovalCard key={a.id} approval={a} />)}
            {alerts.length === 0 && approvals.length === 0 && (
              <div className="rounded-lg border border-dashed border-green-900 p-6 text-center">
                <div className="text-3xl text-green-700">✓</div>
                <div className="mt-1 text-base font-bold text-green-500">All clear</div>
                <div className="mt-1 text-xs text-green-800">Alerts and Bot requests appear here.</div>
              </div>
            )}
          </div>
          <div className="border-t border-edge p-2">
            <div className="px-2 pb-1 text-xs font-bold uppercase tracking-widest text-green-700">Bots</div>
            <BotRoster roster={snap?.bots.roster ?? []} hasOutput={(r) => outputs.some((o) => o.role === r)} onOpen={openRole} />
          </div>
        </aside>
      </div>
    </div>
  );
}
