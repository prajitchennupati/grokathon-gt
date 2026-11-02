import { useEffect, useRef, useState } from "react";
import type { AircraftView, ScenarioStatic, SimSnapshot, XY } from "../api";

interface Props {
  scenario: ScenarioStatic;
  sim: SimSnapshot;
  selected: string | null;
  onSelect: (callsign: string | null) => void;
  /** Callsigns to draw as conflicting (red). */
  conflicts?: string[];
}

const C = {
  ring: "rgba(57,255,122,0.16)",
  ringLabel: "rgba(57,255,122,0.4)",
  runway: "#d9e6df",
  centerline: "rgba(200,220,210,0.35)",
  fix: "rgba(46,230,255,0.55)",
  sector: "rgba(120,140,255,0.12)",
  target: "#39ff7a",
  vfr: "#f2f27a",
  select: "#2ee6ff",
  conflict: "#ff4545",
  wxFill: { light: "rgba(40,120,60,0.25)", moderate: "rgba(150,150,40,0.28)", heavy: "rgba(190,120,20,0.32)", extreme: "rgba(200,40,40,0.35)" } as Record<string, string>,
  wxEdge: "rgba(230,170,40,0.75)",
};

const TRAIL = 6;
const RING_NM = 5;
const MAX_RING_NM = 45;

export default function Scope({ scenario, sim, selected, onSelect, conflicts = [] }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const trails = useRef<Map<string, XY[]>>(new Map());
  const lastT = useRef<number>(-1);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [view, setView] = useState({ scale: 11, cx: 0, cy: 0 }); // px per nm, center in nm
  const fitted = useRef(false);

  // fit ~32 nm around the airport the first time the pane has a real size
  const userMoved = useRef(false);
  useEffect(() => {
    if (userMoved.current || size.w < 100 || size.h < 100) return;
    fitted.current = true;
    setView({ scale: Math.min(size.w, size.h) / 64, cx: 0, cy: 0 });
  }, [size.w, size.h]);
  const drag = useRef<{ x: number; y: number; cx: number; cy: number; moved: boolean } | null>(null);
  const [, setBlink] = useState(0);

  // conflict targets flash independently of the sim tick
  useEffect(() => {
    if (!conflicts.length) return;
    const id = window.setInterval(() => setBlink((b) => b + 1), 250);
    return () => window.clearInterval(id);
  }, [conflicts.length]);

  // history trails, one dot per sim second
  if (sim.t !== lastT.current) {
    if (sim.t < lastT.current) trails.current.clear();
    lastT.current = sim.t;
    const live = new Set<string>();
    for (const a of sim.aircraft) {
      live.add(a.callsign);
      const tr = trails.current.get(a.callsign) ?? [];
      tr.push([a.x, a.y]);
      if (tr.length > TRAIL + 1) tr.shift();
      trails.current.set(a.callsign, tr);
    }
    for (const k of [...trails.current.keys()]) if (!live.has(k)) trails.current.delete(k);
  }

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const measure = () => {
      const r = el.getBoundingClientRect();
      setSize((s) => (s.w === r.width && s.h === r.height ? s : { w: r.width, h: r.height }));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    window.addEventListener("resize", measure);
    return () => { ro.disconnect(); window.removeEventListener("resize", measure); };
  }, []);

  const toPx = (x: number, y: number): XY => [size.w / 2 + (x - view.cx) * view.scale, size.h / 2 - (y - view.cy) * view.scale];
  const toNm = (px: number, py: number): XY => [view.cx + (px - size.w / 2) / view.scale, view.cy - (py - size.h / 2) / view.scale];

  useEffect(() => {
    const cv = canvas.current;
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = size.w * dpr;
    cv.height = size.h * dpr;
    const g = cv.getContext("2d")!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw(g);
  });

  function draw(g: CanvasRenderingContext2D) {
    g.fillStyle = "#000";
    g.fillRect(0, 0, size.w, size.h);
    g.font = "12px var(--font-mono), monospace";
    g.textBaseline = "middle";

    // sectors
    for (const s of scenario.sectors) {
      g.strokeStyle = C.sector;
      g.setLineDash([2, 6]);
      poly(g, s.polygon_xy, false);
      g.stroke();
      g.setLineDash([]);
    }

    // range rings around the ARP
    const [ox, oy] = toPx(0, 0);
    g.lineWidth = 1;
    for (let r = RING_NM; r <= MAX_RING_NM; r += RING_NM) {
      g.strokeStyle = C.ring;
      g.beginPath();
      g.arc(ox, oy, r * view.scale, 0, Math.PI * 2);
      g.stroke();
      if (r % 10 === 0) {
        g.fillStyle = C.ringLabel;
        g.fillText(`${r}`, ox + 3, oy - r * view.scale + 8);
      }
    }

    // weather
    for (const w of sim.weather) {
      g.fillStyle = C.wxFill[w.intensity] ?? C.wxFill.heavy;
      g.strokeStyle = C.wxEdge;
      g.lineWidth = 1.5;
      poly(g, w.polygon_xy, true);
      g.fill();
      g.stroke();
      const cx = w.polygon_xy.reduce((s, p) => s + p[0], 0) / w.polygon_xy.length;
      const cy = w.polygon_xy.reduce((s, p) => s + p[1], 0) / w.polygon_xy.length;
      const [px, py] = toPx(cx, cy);
      g.fillStyle = C.wxEdge;
      g.textAlign = "center";
      g.fillText(`WX ${w.intensity.toUpperCase()}`, px, py);
      g.textAlign = "left";
    }

    // extended centerlines (dashed) and runways
    for (const rw of scenario.runways) {
      const [tx, ty] = rw.thr;
      const [ex, ey] = rw.end;
      const len = Math.hypot(ex - tx, ey - ty) || 1;
      const ux = (tx - ex) / len, uy = (ty - ey) / len;
      g.strokeStyle = C.centerline;
      g.lineWidth = 1;
      g.setLineDash([6, 6]);
      line(g, toPx(tx, ty), toPx(tx + ux * rw.final_nm, ty + uy * rw.final_nm));
      g.setLineDash([]);
      for (let m = 5; m <= rw.final_nm; m += 5) {
        const [mx, my] = toPx(tx + ux * m, ty + uy * m);
        g.beginPath();
        g.moveTo(mx - uy * 4, my - ux * 4);
        g.lineTo(mx + uy * 4, my + ux * 4);
        g.stroke();
      }
      g.strokeStyle = C.runway;
      g.lineWidth = 3;
      line(g, toPx(tx, ty), toPx(ex, ey));
      g.fillStyle = C.runway;
      const [lx, ly] = toPx(tx + ux * 0.6, ty + uy * 0.6);
      g.fillText(rw.id, lx + 2, ly - 7);
    }

    // fixes
    for (const f of scenario.fixes) {
      if (f.kind === "runway") continue;
      const [px, py] = toPx(f.xy[0], f.xy[1]);
      g.strokeStyle = C.fix;
      g.lineWidth = 1;
      g.beginPath();
      g.moveTo(px, py - 4);
      g.lineTo(px + 4, py + 3);
      g.lineTo(px - 4, py + 3);
      g.closePath();
      g.stroke();
      g.fillStyle = C.fix;
      g.font = "10px var(--font-mono), monospace";
      g.fillText(f.id, px + 6, py);
      g.font = "12px var(--font-mono), monospace";
    }

    // targets
    const conflictSet = new Set(conflicts);
    // minor traffic first so airliners' data blocks draw on top
    const ordered = [...sim.aircraft].sort((a, b) => Number(!!b.minor) - Number(!!a.minor));
    for (const a of ordered) drawTarget(g, a, conflictSet.has(a.callsign));
  }

  function drawTarget(g: CanvasRenderingContext2D, a: AircraftView, inConflict: boolean) {
    const sel = a.callsign === selected;
    if (a.minor && !sel && !inConflict) {
      // light GA in live mode: a dim dot, no data block
      const [mx, my] = toPx(a.x, a.y);
      g.fillStyle = "rgba(57,255,122,0.35)";
      g.fillRect(mx - 2, my - 2, 4, 4);
      return;
    }
    const flash = inConflict && Math.floor(Date.now() / 500) % 2 === 0;
    const color = inConflict ? C.conflict : sel ? C.select : a.flight_rules === "VFR" ? C.vfr : C.target;
    const [px, py] = toPx(a.x, a.y);

    const tr = trails.current.get(a.callsign) ?? [];
    tr.slice(0, -1).forEach(([x, y], i) => {
      const [hx, hy] = toPx(x, y);
      g.fillStyle = `rgba(57,255,122,${0.12 + (i / TRAIL) * 0.35})`;
      g.fillRect(hx - 1.5, hy - 1.5, 3, 3);
    });

    // 60-second velocity vector
    const h = (a.heading * Math.PI) / 180;
    const vnm = a.gs_kt / 60;
    g.strokeStyle = color;
    g.globalAlpha = 0.5;
    g.lineWidth = 1;
    line(g, [px, py], toPx(a.x + Math.sin(h) * vnm, a.y + Math.cos(h) * vnm));
    g.globalAlpha = 1;

    g.fillStyle = color;
    g.strokeStyle = color;
    if (inConflict && flash) {
      g.beginPath();
      g.arc(px, py, 9, 0, Math.PI * 2);
      g.stroke();
    }
    g.fillRect(px - 3, py - 3, 6, 6);
    if (sel) g.strokeRect(px - 7, py - 7, 14, 14);

    // leader line + 2-line data block
    const lx = px + 18, ly = py - 18;
    line(g, [px + 3, py - 3], [lx - 2, ly + 6]);
    const alt = String(Math.round(a.alt_ft / 100)).padStart(3, "0");
    const trend = a.vs_fpm > 300 ? "↑" : a.vs_fpm < -300 ? "↓" : " ";
    g.fillText(a.callsign, lx, ly);
    g.fillText(`${alt}${trend}${String(a.gs_kt).padStart(3, " ")}`, lx, ly + 12);
  }

  function poly(g: CanvasRenderingContext2D, pts: XY[], close: boolean) {
    g.beginPath();
    pts.forEach(([x, y], i) => {
      const [px, py] = toPx(x, y);
      i ? g.lineTo(px, py) : g.moveTo(px, py);
    });
    if (close) g.closePath();
  }

  function line(g: CanvasRenderingContext2D, a: XY, b: XY) {
    g.beginPath();
    g.moveTo(a[0], a[1]);
    g.lineTo(b[0], b[1]);
    g.stroke();
  }

  function pick(px: number, py: number): string | null {
    let best: string | null = null;
    let bestD = 14;
    for (const a of sim.aircraft) {
      const [ax, ay] = toPx(a.x, a.y);
      const d = Math.min(Math.hypot(ax - px, ay - py), Math.hypot(ax + 30 - px, ay - 12 - py)); // target or data block
      if (d < bestD) { bestD = d; best = a.callsign; }
    }
    return best;
  }

  return (
    <div ref={wrap} className="absolute inset-0 overflow-hidden bg-black select-none">
      <canvas
        ref={canvas}
        style={{ width: size.w, height: size.h }}
        className="absolute left-0 top-0 cursor-crosshair"
        onWheel={(e) => {
          userMoved.current = true;
          const [nx, ny] = toNm(e.nativeEvent.offsetX, e.nativeEvent.offsetY);
          const scale = Math.min(60, Math.max(3, view.scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
          // zoom about the cursor
          setView({ scale, cx: nx - (e.nativeEvent.offsetX - size.w / 2) / scale, cy: ny + (e.nativeEvent.offsetY - size.h / 2) / scale });
        }}
        onMouseDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, cx: view.cx, cy: view.cy, moved: false }; }}
        onMouseMove={(e) => {
          const d = drag.current;
          if (!d) return;
          const dx = e.clientX - d.x, dy = e.clientY - d.y;
          if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
          if (d.moved) userMoved.current = true;
          if (d.moved) setView((v) => ({ ...v, cx: d.cx - dx / v.scale, cy: d.cy + dy / v.scale }));
        }}
        onMouseUp={(e) => {
          const d = drag.current;
          drag.current = null;
          if (d && !d.moved) onSelect(pick(e.nativeEvent.offsetX, e.nativeEvent.offsetY));
        }}
        onMouseLeave={() => { drag.current = null; }}
      />
      <div className="pointer-events-none absolute bottom-2 right-3 text-[10px] text-green-900">
        rings {RING_NM} nm · scroll zoom · drag pan
      </div>
    </div>
  );
}
