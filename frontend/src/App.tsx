import { useEffect, useState } from "react";
import Scope from "./components/Scope";
import { fmtT, simControl, useScenario, useSnapshot } from "./api";

export default function App() {
  const scenario = useScenario();
  const { snap, connected } = useSnapshot();
  const [selected, setSelected] = useState<string | null>(null);
  const sim = snap?.sim;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT" || (e.target as HTMLElement)?.tagName === "TEXTAREA") return;
      if (e.code === "Space") { e.preventDefault(); simControl("toggle"); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const sel = sim?.aircraft.find((a) => a.callsign === selected);

  return (
    <div className="flex h-full flex-col bg-black text-[13px]">
      <header className="flex items-center gap-4 border-b border-edge bg-panel px-4 py-2">
        <div className="text-lg font-bold tracking-widest text-target">CLEARANCE</div>
        <div className="text-xs text-green-600">{scenario ? `${scenario.facility} · ${scenario.position}` : "…"}</div>
        <div className="mx-auto rounded border border-amber-500 bg-amber-500/10 px-3 py-1 text-xs font-bold tracking-wider text-amber-400">
          ADVISORY PROTOTYPE — NOT FOR OPERATIONAL USE
        </div>
        <div className={`text-xs ${connected ? "text-green-500" : "text-red-500"}`}>{connected ? "● LIVE" : "○ RECONNECTING"}</div>
      </header>

      <div className="flex min-h-0 flex-1">
        <main className="relative min-w-0 flex-1">
          {scenario && sim ? (
            <Scope scenario={scenario} sim={sim} selected={selected} onSelect={setSelected} />
          ) : (
            <div className="p-8 text-green-700">Connecting to backend…</div>
          )}
        </main>

        <aside className="flex w-[380px] flex-col gap-3 overflow-y-auto border-l border-edge bg-panel p-3">
          {sim && (
            <section className="rounded border border-edge p-3">
              <div className="flex items-baseline justify-between">
                <div className="text-2xl font-bold text-target">{fmtT(sim.t)}</div>
                <div className="text-xs text-green-700">of {fmtT(sim.duration_s)} · {sim.aircraft.length} tracks</div>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <Btn onClick={() => simControl(sim.running ? "pause" : "resume")}>{sim.running ? "❚❚ Pause" : "▶ Run"}</Btn>
                <Btn onClick={() => simControl("restart")}>⟲ Restart</Btn>
                {[1, 2, 4].map((s) => (
                  <Btn key={s} active={sim.speed === s} onClick={() => simControl("speed", s)}>{s}x</Btn>
                ))}
              </div>
              <div className="mt-2 h-1 w-full bg-edge">
                <div className="h-1 bg-target" style={{ width: `${(sim.t / sim.duration_s) * 100}%` }} />
              </div>
            </section>
          )}

          <section className="rounded border border-edge p-3">
            <div className="mb-1 text-xs uppercase tracking-wider text-green-700">Selected</div>
            {sel ? (
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <div className="col-span-2 text-base font-bold text-select">{sel.callsign} <span className="text-green-600">{sel.type}</span></div>
                <div>ALT {sel.alt_ft} ft</div><div>ASSIGNED {sel.tgt_alt_ft}</div>
                <div>HDG {Math.round(sel.heading)}°</div><div>GS {sel.gs_kt} kt</div>
                <div>VS {sel.vs_fpm} fpm</div><div>{sel.vector ? "ON VECTOR" : `→ ${sel.next_fix ?? "—"}`}</div>
                <div>{sel.origin} → {sel.destination}</div><div>{sel.land ? `RWY ${sel.land}` : sel.flight_rules}</div>
              </div>
            ) : (
              <div className="text-xs text-green-800">Click a target on the scope.</div>
            )}
          </section>

          {sim && (
            <section className="rounded border border-edge p-3">
              <div className="mb-1 text-xs uppercase tracking-wider text-green-700">Scenario events</div>
              {sim.events_fired.map((e, i) => (
                <div key={i} className="text-xs"><span className="text-green-700">{fmtT(e.t)}</span> {e.title}</div>
              ))}
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}

export function Btn({ children, onClick, active, danger, disabled }: {
  children: React.ReactNode; onClick?: () => void; active?: boolean; danger?: boolean; disabled?: boolean;
}) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className={`rounded border px-2 py-1 text-xs font-bold transition disabled:opacity-40 ${
        danger ? "border-red-600 text-red-400 hover:bg-red-900/40"
        : active ? "border-target bg-target/20 text-target"
        : "border-edge text-green-400 hover:border-target hover:text-target"
      }`}
    >
      {children}
    </button>
  );
}
