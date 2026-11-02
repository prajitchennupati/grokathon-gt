import { useEffect, useRef, useState } from "react";

export type XY = [number, number];

export interface Runway { id: string; thr: XY; end: XY; final_nm: number; active: boolean }
export interface Fix { id: string; kind: "fix" | "faf" | "runway"; xy: XY }
export interface ScenarioStatic {
  name: string;
  description: string;
  facility: string;
  position: string;
  airport: { icao: string; name: string; lat: number; lon: number; elevation_ft: number };
  duration_s: number;
  runways: Runway[];
  fixes: Fix[];
  sectors: { id: string; name: string; polygon_xy: XY[] }[];
  events: { t: number; kind: string; title: string }[];
}

export interface AircraftView {
  callsign: string;
  type: string;
  x: number;
  y: number;
  alt_ft: number;
  tgt_alt_ft: number;
  heading: number;
  gs_kt: number;
  vs_fpm: number;
  next_fix: string | null;
  vector: boolean;
  land: string | null;
  flight_rules: string;
  origin: string;
  destination: string;
}

export interface WeatherView { id: string; title: string; intensity: string; polygon_xy: XY[]; affects_fix: string | null }

export interface SimSnapshot {
  t: number;
  duration_s: number;
  running: boolean;
  finished: boolean;
  speed: number;
  aircraft: AircraftView[];
  landed: { callsign: string; runway: string; t: number }[];
  weather: WeatherView[];
  events_fired: { t: number; kind: string; title: string; detail: string }[];
}

export interface Snapshot {
  type: "snapshot";
  sim: SimSnapshot;
  demo_mode: boolean;
}

export async function api<T = unknown>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const simControl = (action: string, value?: number) => api("/api/sim/control", { action, value });

/** Live snapshot stream with auto-reconnect. */
export function useSnapshot(): { snap: Snapshot | null; connected: boolean } {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const retry = useRef<number | undefined>(undefined);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => setConnected(true);
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === "snapshot") setSnap(msg);
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry.current = window.setTimeout(connect, 1000);
      };
    };
    connect();
    return () => {
      closed = true;
      window.clearTimeout(retry.current);
      ws?.close();
    };
  }, []);

  return { snap, connected };
}

export function useScenario(): ScenarioStatic | null {
  const [s, setS] = useState<ScenarioStatic | null>(null);
  useEffect(() => {
    const load = () => api<ScenarioStatic>("/api/scenario").then(setS).catch(() => window.setTimeout(load, 1000));
    load();
  }, []);
  return s;
}

export const fmtT = (t: number) => `T+${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
