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

export interface SuggestionView { callsign: string; action: "climb" | "descend" | "turn" | "speed"; value: number; phraseology: string }

export interface AlertView {
  id: number;
  key: string;
  a: string;
  b: string;
  created_t: number;
  severity: "predicted" | "imminent";
  max_severity: string;
  geometry: { t_cpa: number; lateral_nm: number; vertical_ft: number; t_los: number; severity: string };
  status: "active" | "resolved";
  resolved_t: number | null;
  advisory_state: "pending" | "ready";
  advisory: { summary: string; suggestion: SuggestionView; rationale: string } | null;
  advisory_source: string;
  advisory_error: string;
  suggestion_valid: boolean;
  validation_note: string;
  decision: "approved" | "dismissed" | null;
  decision_t: number | null;
  min_sep: { t: number; lateral_nm: number; vertical_ft: number } | null;
}

export interface LogEntry { id: number; t_sim: number; ts: number; kind: string; actor: string; message: string; data: Record<string, unknown> }

export type Role = "briefing" | "relief" | "coordination" | "paperwork";

export interface BotView {
  role: Role;
  name: string;
  title: string;
  mode: "live" | "fallback";
  status: "idle" | "working" | "waiting_for_approval";
  working_since: number | null;
  working_reason: string;
  last_output_ts: number | null;
  last_output_t_sim: number | null;
  tasks_completed: number;
  pending_approvals: number;
  note: string;
}

export interface BotOutputView {
  id: number;
  role: Role;
  kind: string;
  title: string;
  body_markdown: string;
  sources: { title: string; url: string }[];
  via: "webhook" | "dropbox" | "fallback";
  llm_source: string;
  t_sim: number;
  ts: number;
  acked: number[];
  checklist: string[];
}

export interface ApprovalView {
  id: number;
  output_id: number;
  role: Role;
  action: { type: string; summary: string; to?: string | null; body?: string };
  status: "pending" | "approved" | "declined";
  t_sim: number;
  decided_t_sim: number | null;
}

export interface Snapshot {
  type: "snapshot";
  sim: SimSnapshot;
  alerts: AlertView[];
  log: LogEntry[];
  bots: {
    roster: BotView[];
    outputs: BotOutputView[];
    approvals: ApprovalView[];
    minutes_saved: Record<string, number>;
    minutes_assumptions: Record<string, number>;
    live_timeout_s: number;
  };
  restrictions: string[];
  metrics: Record<string, number>;
  demo_mode: boolean;
  auto_pause: boolean;
  llm: { enabled: boolean; offline: boolean; model: string | null };
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
export const decideApproval = (id: number, decision: "approve" | "decline") => api(`/api/approvals/${id}`, { decision });
export const runBot = (role: Role, fallback = false) => api(`/api/bots/${role}/run`, { fallback });
export const setBotMode = (role: Role, mode: "live" | "fallback") => api(`/api/bots/${role}/mode`, { mode });
export const ackItem = (outputId: number, item: number) => api(`/api/bots/outputs/${outputId}/ack`, { item });
export const decideAlert = (id: number, decision: "approve" | "dismiss") => api(`/api/alerts/${id}/decision`, { decision });

/** Alerts the controller still needs to act on, most urgent first. */
export function actionableAlerts(alerts: AlertView[]): AlertView[] {
  return alerts
    .filter((a) => a.status === "active")
    .sort((x, y) => (x.severity === y.severity ? x.geometry.t_cpa - y.geometry.t_cpa : x.severity === "imminent" ? -1 : 1));
}

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
