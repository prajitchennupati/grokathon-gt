import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { AircraftView, ScenarioStatic, SimSnapshot, XY } from "../api";
import { flightName, ft, isBig } from "../friendly";

export interface ConflictLine { a: string; b: string; label: string }

interface Props {
  scenario: ScenarioStatic;
  sim: SimSnapshot;
  selected: string | null;
  onSelect: (callsign: string | null) => void;
  conflicts?: ConflictLine[];
  theme: "dark" | "light";
}

// Esri Canvas basemaps: keyless, with a separate place-name layer on top. (CARTO now needs an API key.)
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas";
const TILES = {
  dark: [`${ESRI}/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`, `${ESRI}/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`],
  light: [`${ESRI}/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`, `${ESRI}/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`],
};
const ATTRIBUTION = "Map &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors";

// Material "flight" glyph (Apache-2.0), nose pointing north
const PLANE_SVG = `<svg viewBox="0 0 24 24"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/></svg>`;

interface Track {
  marker: L.Marker;
  glyph: HTMLElement;
  label: HTMLElement;
  ac: AircraftView;
  t0: number;
}

/** Real map with Flightradar-style plane icons. Positions glide between sim ticks. */
export default function Scope({ scenario, sim, selected, onSelect, conflicts = [], theme }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const tiles = useRef<L.TileLayer[]>([]);
  const tracks = useRef<Map<string, Track>>(new Map());
  const staticLayer = useRef<L.LayerGroup | null>(null);
  const wxLayer = useRef<L.LayerGroup | null>(null);
  const conflictLayer = useRef<L.LayerGroup | null>(null);
  const trail = useRef<{ cs: string | null; pts: L.LatLngTuple[]; line: L.Polyline | null }>({ cs: null, pts: [], line: null });
  const motion = useRef({ running: sim.running, speed: sim.speed });
  const lines = useRef<{ c: ConflictLine; line: L.Polyline; tag: L.Marker }[]>([]);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  const { lat: lat0, lon: lon0 } = scenario.airport;
  const toLL = ([x, y]: XY): L.LatLngTuple => [lat0 + y / 60, lon0 + x / (60 * Math.cos((lat0 * Math.PI) / 180))];

  // ---- map setup ---------------------------------------------------------
  useEffect(() => {
    if (!box.current || map.current) return;
    const m = L.map(box.current, { zoomControl: false, attributionControl: true, zoomSnap: 0.25 });
    L.control.zoom({ position: "bottomright" }).addTo(m);
    m.attributionControl.setPrefix(false);
    const d = 30 / 60; // ~30 nm around the airport
    m.fitBounds([[lat0 - d, lon0 - d * 1.2], [lat0 + d, lon0 + d * 1.2]]);
    m.on("click", () => onSelectRef.current(null));
    staticLayer.current = L.layerGroup().addTo(m);
    wxLayer.current = L.layerGroup().addTo(m);
    conflictLayer.current = L.layerGroup().addTo(m);
    map.current = m;
    const ro = new ResizeObserver(() => m.invalidateSize());
    ro.observe(box.current);
    return () => { ro.disconnect(); m.remove(); map.current = null; tracks.current.clear(); };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    tiles.current.forEach((t) => t.remove());
    const [base, labels] = TILES[theme];
    tiles.current = [
      L.tileLayer(base, { attribution: ATTRIBUTION, maxZoom: 16 }).addTo(m),
      L.tileLayer(labels, { maxZoom: 16, opacity: 0.9 }).addTo(m),
    ];
  }, [theme]);

  // ---- runways + airport label -------------------------------------------
  useEffect(() => {
    const g = staticLayer.current;
    if (!g) return;
    g.clearLayers();
    for (const rw of scenario.runways) {
      L.polyline([toLL(rw.thr), toLL(rw.end)], { color: theme === "dark" ? "#e5e7eb" : "#334155", weight: 4, opacity: 0.9, interactive: false }).addTo(g);
    }
    L.marker([lat0 - 0.035, lon0], {
      interactive: false,
      icon: L.divIcon({ className: "airport-label", html: `<span>ATL · Atlanta airport</span>`, iconSize: [0, 0] }),
    }).addTo(g);
  }, [scenario, theme]);

  // ---- weather -------------------------------------------------------------
  useEffect(() => {
    const g = wxLayer.current;
    if (!g) return;
    g.clearLayers();
    for (const w of sim.weather) {
      L.polygon(w.polygon_xy.map(toLL), { color: "#f59e0b", weight: 2, fillColor: "#f59e0b", fillOpacity: 0.3, interactive: false })
        .bindTooltip("⛈ Storm", { permanent: true, direction: "center", className: "wx-label" })
        .addTo(g);
    }
  }, [sim.weather.length, sim.t]);

  // ---- planes ----------------------------------------------------------------
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    motion.current = { running: sim.running, speed: sim.speed };
    const now = performance.now();
    const present = new Set<string>();
    const inConflict = new Set(conflicts.flatMap((c) => [c.a, c.b]));

    for (const ac of sim.aircraft) {
      present.add(ac.callsign);
      let tr = tracks.current.get(ac.callsign);
      if (!tr) {
        const el = document.createElement("div");
        el.className = "plane";
        el.innerHTML = `<div class="plane-glyph">${PLANE_SVG}</div><div class="plane-label"></div>`;
        const cs = ac.callsign;
        const marker = L.marker([ac.lat, ac.lon], { icon: L.divIcon({ className: "plane-icon", html: el, iconSize: [0, 0] }), keyboard: false })
          .on("click", (e) => { L.DomEvent.stopPropagation(e); onSelectRef.current(cs); })
          .addTo(m);
        tr = { marker, glyph: el.querySelector<HTMLElement>(".plane-glyph")!, label: el.querySelector<HTMLElement>(".plane-label")!, ac, t0: now };
        tracks.current.set(cs, tr);
      }
      tr.ac = ac;
      tr.t0 = now;
      tr.marker.setLatLng([ac.lat, ac.lon]);
      const big = isBig(ac);
      const sel = ac.callsign === selected;
      const hot = inConflict.has(ac.callsign);
      tr.glyph.style.transform = `rotate(${ac.heading}deg)`;
      tr.glyph.className = `plane-glyph ${big ? "big" : "small"}${sel ? " sel" : ""}${hot ? " hot" : ""}`;
      tr.label.style.display = sel || hot || big ? "" : "none";
      tr.label.className = `plane-label${hot ? " hot" : sel ? " sel" : ""}`;
      tr.label.innerHTML = `${flightName(ac.callsign)}${sel || hot ? `<br><b>${ft(ac.alt_ft)}</b>` : ""}`;
      tr.marker.setZIndexOffset(hot ? 1000 : sel ? 900 : big ? 100 : 0);
    }
    for (const [cs, tr] of tracks.current) {
      if (!present.has(cs)) { tr.marker.remove(); tracks.current.delete(cs); }
    }

    // trail for the selected plane only
    const t = trail.current;
    if (t.cs !== selected) { t.line?.remove(); t.cs = selected; t.pts = []; t.line = null; }
    const selAc = sim.aircraft.find((a) => a.callsign === selected);
    if (selAc) {
      t.pts.push([selAc.lat, selAc.lon]);
      if (t.pts.length > 120) t.pts.shift();
      if (!t.line) t.line = L.polyline(t.pts, { color: "#22d3ee", weight: 2, opacity: 0.7, interactive: false }).addTo(m);
      else t.line.setLatLngs(t.pts);
    }

    // red link between planes that are too close
    const g = conflictLayer.current!;
    g.clearLayers();
    lines.current = conflicts.map((c) => ({
      c,
      line: L.polyline([[0, 0], [0, 0]], { color: "#ef4444", weight: 3, dashArray: "6 6", interactive: false }).addTo(g),
      tag: L.marker([0, 0], { interactive: false, icon: L.divIcon({ className: "conflict-tag", html: `<span>${c.label}</span>`, iconSize: [0, 0] }) }).addTo(g),
    }));
  }, [sim, selected, conflicts]);

  // ---- smooth motion between ticks -------------------------------------------
  useEffect(() => {
    let raf = 0;
    const frame = () => {
      const now = performance.now();
      const { running, speed } = motion.current;
      const pos = new Map<string, L.LatLngTuple>();
      for (const [cs, tr] of tracks.current) {
        const dt = running ? Math.min(2, (now - tr.t0) / 1000) * speed : 0;
        const h = (tr.ac.heading * Math.PI) / 180;
        const nm = (tr.ac.gs_kt / 3600) * dt;
        const ll: L.LatLngTuple = [
          tr.ac.lat + (nm * Math.cos(h)) / 60,
          tr.ac.lon + (nm * Math.sin(h)) / (60 * Math.cos((tr.ac.lat * Math.PI) / 180)),
        ];
        pos.set(cs, ll);
        if (dt > 0) tr.marker.setLatLng(ll);
      }
      for (const { c, line, tag } of lines.current) {
        const a = pos.get(c.a), b = pos.get(c.b);
        if (!a || !b) continue;
        line.setLatLngs([a, b]);
        tag.setLatLng([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  return <div ref={box} className={`absolute inset-0 ${theme === "dark" ? "bg-[#0e1117]" : "bg-[#e8eaed]"}`} />;
}
