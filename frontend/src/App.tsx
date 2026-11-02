import { useEffect, useMemo, useRef, useState } from "react";
import Scope, { type ConflictLine } from "./components/Scope";
import { AlertCard } from "./components/AlertPanel";
import { ApprovalCard } from "./components/ApprovalQueue";
import BotRoster, { HelperSettings } from "./components/BotRoster";
import BriefingView from "./components/BriefingView";
import ShiftLog from "./components/ShiftLog";
import MetricsStrip, { minutesAssumptions } from "./components/MetricsStrip";
import DemoStepper from "./components/DemoStepper";
import Intro from "./components/Intro";
import { actionableAlerts, decideAlert, fmtT, setSource, simControl, useScenario, useSnapshot, type Snapshot } from "./api";
import { flightName, ft, knotsMph, typeName, verticalWord } from "./friendly";

type Drawer = null | "doc" | "log";

function stored<T extends string>(key: string, fallback: T): T {
  try { return (localStorage.getItem(key) as T) || fallback; } catch { return fallback; }
}
function store(key: string, v: string) {
  try { localStorage.setItem(key, v); } catch { /* private mode */ }
}

export default function App() {
  const { snap, connected } = useSnapshot();
  const live = snap?.source === "live";
  const scenario = useScenario(`${snap?.source ?? ""}:${snap?.sim.live?.flow ?? ""}`);
  const [selected, setSelected] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [outputId, setOutputId] = useState<number | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const q = new URLSearchParams(location.search).get("theme");
    return q === "light" || q === "dark" ? q : stored("clearance.theme", "dark");
  });
  const [intro, setIntro] = useState(() => !new URLSearchParams(location.search).has("nointro"));
  const [caption, setCaption] = useState<string | null>(null);
  const nextStep = useRef<(() => void) | null>(null);
  const sim = snap?.sim;
  const outputs = snap?.bots.outputs ?? [];

  // pop each new document open as it arrives, unless it's only approval items (shown as cards)
  const seenOutputs = useRef(0);
  useEffect(() => {
    if (outputs.length > seenOutputs.current) {
      const fresh = outputs.slice(seenOutputs.current).filter((o) => o.kind !== "coordination_drafts");
      if (fresh.length) { setOutputId(fresh[fresh.length - 1].id); setDrawer("doc"); }
    }
    seenOutputs.current = outputs.length;
  }, [outputs.length]);

  // a new conflict takes priority over any open document
  const activeAlerts = (snap?.alerts ?? []).filter((a) => a.status === "active");
  const newestAlert = activeAlerts.length ? Math.max(...activeAlerts.map((a) => a.id)) : 0;
  useEffect(() => { if (newestAlert) setDrawer(null); }, [newestAlert]);

  // keyboard: N next · A approve · D dismiss · Space pause · Esc close
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
      else if (e.key === "n" || e.key === "N") { setIntro(false); nextStep.current?.(); }
      else if (e.key === "Escape") { setDrawer(null); setIntro(false); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // decided alerts linger a few seconds so the outcome is visible, then leave
  const alerts = actionableAlerts(snap?.alerts ?? []).filter((a) => !a.decision || (sim && a.decision_t !== null && sim.t - a.decision_t < 8));
  const approvals = (snap?.bots.approvals ?? []).filter((a) => a.status === "pending");
  const conflictKey = activeAlerts.map((a) => `${a.key}:${a.geometry.lateral_nm}`).join(",");
  const conflictLines = useMemo<ConflictLine[]>(
    () => activeAlerts.map((a) => ({ a: a.a, b: a.b, label: `${a.geometry.lateral_nm} nm apart` })),
    [conflictKey],
  );
  const sel = sim?.aircraft.find((a) => a.callsign === selected);
  const openRole = (role: string) => {
    const o = [...outputs].reverse().find((x) => x.role === role);
    if (o) { setOutputId(o.id); setDrawer("doc"); }
  };
  const toggleTheme = () => { const t = theme === "dark" ? "light" : "dark"; setTheme(t); store("clearance.theme", t); };

  return (
    <div className="relative flex h-full flex-col bg-[#0b0f14] text-sm text-gray-100">
      {/* ---------------------------------------------------------------- header */}
      <header className="flex items-center gap-4 border-b border-gray-800 bg-[#0f141a] px-4 py-2">
        <div className="text-lg font-bold tracking-[0.2em] text-green-400">CLEARANCE</div>

        <div className="flex overflow-hidden rounded-lg border border-gray-700 text-xs font-bold">
          {(["scenario", "live"] as const).map((src) => (
            <button key={src} onClick={() => setSource(src)}
              className={`px-3 py-1.5 ${snap?.source === src ? (src === "live" ? "bg-red-600 text-white" : "bg-green-500 text-black") : "text-gray-400 hover:text-white"}`}>
              {src === "live" ? "● Live Atlanta" : "Guided demo"}
            </button>
          ))}
        </div>

        {sim && (
          <div className="flex items-center gap-2">
            {!live && (
              <button onClick={() => simControl(sim.running ? "pause" : "resume")} title="Pause / play (Space)"
                className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-800 text-green-400 hover:bg-gray-700">
                {sim.running ? "❚❚" : "▶"}
              </button>
            )}
            <span className="text-lg font-bold tabular-nums text-gray-100">
              {live ? new Date().toUTCString().slice(17, 22) + " UTC" : fmtT(sim.t).replace("T+", "")}
            </span>
          </div>
        )}

        {snap && snap.metrics.minutes_saved > 0 && (
          <div className="rounded-full bg-green-900/40 px-3 py-1 text-xs text-green-300" title={`Rough estimate of controller time saved. Assumes: ${minutesAssumptions(snap)}`}>
            ⏱ <b>{snap.metrics.minutes_saved} min</b> of paperwork saved
          </div>
        )}

        <div className="ml-auto flex items-center gap-3 text-xs">
          <button onClick={toggleTheme} className="text-gray-400 hover:text-white" title="Map style">{theme === "dark" ? "☀ Light map" : "☾ Dark map"}</button>
          <button onClick={() => setDrawer(drawer === "log" ? null : "log")} className="text-gray-400 hover:text-white">History</button>
          <button onClick={() => setIntro(true)} className="flex h-6 w-6 items-center justify-center rounded-full border border-gray-600 text-gray-300 hover:text-white" title="How this works">?</button>
          {!connected && <span className="text-red-400">○ reconnecting</span>}
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* ---------------------------------------------------------------- map */}
        <main className="relative min-w-0 flex-1">
          {scenario && sim ? (
            <Scope scenario={scenario} sim={sim} selected={selected} onSelect={setSelected} conflicts={conflictLines} theme={theme} />
          ) : (
            <div className="p-8 text-gray-500">Connecting…</div>
          )}

          {/* top-left: what am I looking at + selected plane */}
          {sim && (
            <div className="pointer-events-none absolute left-3 top-3 z-[500] space-y-2">
              {live && (
                <div className="rounded-lg bg-black/75 px-3 py-1.5 text-xs text-gray-300">
                  🔴 Live · <b>{sim.aircraft.length}</b> planes near Atlanta · source {sim.live?.provider || "connecting…"}
                  {sim.live?.error && <span className="text-amber-400"> · feed error, showing the last update</span>}
                </div>
              )}
              {sel && (
                <div className="pointer-events-auto w-64 rounded-xl border border-cyan-700 bg-black/85 p-3 text-xs shadow-xl">
                  <div className="flex items-start">
                    <div>
                      <div className="text-base font-bold text-cyan-300">{flightName(sel.callsign)}</div>
                      <div className="text-gray-400">{typeName(sel.type)}</div>
                    </div>
                    <button onClick={() => setSelected(null)} className="ml-auto text-gray-500 hover:text-white">✕</button>
                  </div>
                  <div className="mt-2 grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-gray-200">
                    <span className="text-gray-500">Height</span><span>{ft(sel.alt_ft)} · {verticalWord(sel)}</span>
                    <span className="text-gray-500">Speed</span><span>{knotsMph(sel.gs_kt)}</span>
                    <span className="text-gray-500">Heading</span><span>{String(Math.round(sel.heading)).padStart(3, "0")}°</span>
                    {sel.origin && <><span className="text-gray-500">Route</span><span>{sel.origin} → {sel.destination}</span></>}
                    {sel.land && <><span className="text-gray-500">Status</span><span>Landing on runway {sel.land}</span></>}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* legend */}
          <div className="pointer-events-none absolute bottom-6 right-14 z-[500] flex gap-3 rounded-lg bg-black/70 px-3 py-1 text-[11px] text-gray-300">
            <span><span className="text-[#ffc400]">✈</span> Airliner</span>
            <span><span className="text-gray-200">✈</span> Small plane</span>
            <span><span className="text-red-500">✈</span> Too close</span>
            <span><span className="text-amber-400">■</span> Storm</span>
          </div>

          {/* bottom-left: one-button demo */}
          {sim && !live && (
            <div className="pointer-events-none absolute bottom-4 left-4 z-[600] flex max-w-[calc(100%-2rem)] flex-col items-start gap-2">
              {caption && (
                <div className="max-w-[540px] rounded-xl bg-black/85 px-4 py-2.5 text-sm leading-snug text-white shadow-lg backdrop-blur">
                  <span className="mr-1 text-amber-400">●</span>{caption}
                </div>
              )}
              <DemoStepper t={sim.t} nextRef={nextStep} onStep={() => setDrawer(null)} onCaption={setCaption} />
            </div>
          )}

          {/* slide-over drawers */}
          {drawer && snap && (
            <div className="absolute inset-y-0 right-0 z-[700] w-[min(520px,85%)] border-l border-gray-800 bg-[#0f141a] shadow-2xl">
              {drawer === "doc" && outputs.length > 0 ? (
                <BriefingView outputs={outputs} selectedId={outputId} onSelect={setOutputId} onClose={() => setDrawer(null)} />
              ) : (
                <div className="flex h-full flex-col">
                  <div className="flex items-center border-b border-gray-800 px-4 py-2">
                    <span className="text-sm font-bold">History</span>
                    <button onClick={() => setDrawer(null)} className="ml-auto text-lg text-gray-500 hover:text-white">✕</button>
                  </div>
                  <MetricsStrip snap={snap} />
                  <HelperSettings roster={snap.bots.roster} />
                  <div className="min-h-0 flex-1"><ShiftLog log={snap.log} /></div>
                </div>
              )}
            </div>
          )}
        </main>

        {/* ---------------------------------------------------------------- right: only what needs a decision */}
        <aside className="flex w-[380px] shrink-0 flex-col border-l border-gray-800 bg-[#0f141a]">
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
            <div className="text-xs font-bold uppercase tracking-widest text-gray-500">Needs your decision</div>
            {alerts.map((a) => <AlertCard key={a.id} alert={a} live={live} onFocus={setSelected} />)}
            {approvals.map((a) => <ApprovalCard key={a.id} approval={a} />)}
            {alerts.length === 0 && approvals.length === 0 && (
              <div className="rounded-xl border border-dashed border-gray-700 p-6 text-center">
                <div className="text-3xl text-green-500">✓</div>
                <div className="mt-1 text-base font-bold text-green-400">All clear</div>
                <div className="mt-1 text-xs text-gray-500">Warnings and requests from the helpers show up here.</div>
              </div>
            )}
          </div>
          <div className="border-t border-gray-800 p-3">
            <div className="pb-2 text-xs font-bold uppercase tracking-widest text-gray-500">AI helpers</div>
            <BotRoster roster={snap?.bots.roster ?? []} hasOutput={(r) => outputs.some((o) => o.role === r)} onOpen={openRole} live={live} />
          </div>
        </aside>
      </div>

      {intro && (
        <Intro
          onClose={() => setIntro(false)}
          onDemo={() => { setIntro(false); setSource("scenario").then(() => nextStep.current?.()); }}
          onLive={() => { setIntro(false); setSource("live"); }}
        />
      )}
    </div>
  );
}
