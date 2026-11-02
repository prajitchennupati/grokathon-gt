/** Plain-language helpers so the interface reads for people who aren't controllers. */
import type { AircraftView, SuggestionView } from "./api";

const AIRLINES: Record<string, string> = {
  DAL: "Delta", SWA: "Southwest", AAL: "American", UAL: "United", JBU: "JetBlue", FFT: "Frontier",
  NKS: "Spirit", ASA: "Alaska", EDV: "Endeavor", SKW: "SkyWest", RPA: "Republic", ENY: "Envoy",
  JIA: "PSA Airlines", AAY: "Allegiant", FDX: "FedEx", UPS: "UPS", GTI: "Atlas Air", ACA: "Air Canada",
  BAW: "British Airways", DLH: "Lufthansa", AFR: "Air France", KLM: "KLM", VIR: "Virgin Atlantic",
  JTL: "Jet Linx", EJA: "NetJets", LXJ: "Flexjet", BPX: "flight school", AMX: "Aeroméxico", WJA: "WestJet",
};

const TYPES: Record<string, string> = {
  A319: "Airbus A319", A320: "Airbus A320", A321: "Airbus A321", A21N: "Airbus A321neo", A20N: "Airbus A320neo",
  A332: "Airbus A330", A333: "Airbus A330", A339: "Airbus A330neo", A359: "Airbus A350", BCS1: "Airbus A220", BCS3: "Airbus A220",
  B712: "Boeing 717", B737: "Boeing 737", B738: "Boeing 737-800", B739: "Boeing 737-900", B38M: "Boeing 737 MAX 8",
  B39M: "Boeing 737 MAX 9", B752: "Boeing 757", B753: "Boeing 757", B763: "Boeing 767", B764: "Boeing 767",
  B772: "Boeing 777", B77W: "Boeing 777", B788: "Boeing 787", B789: "Boeing 787", CRJ2: "Bombardier CRJ200",
  CRJ7: "Bombardier CRJ700", CRJ9: "Bombardier CRJ900", E170: "Embraer 170", E75L: "Embraer 175", E75S: "Embraer 175",
  E145: "Embraer 145", GLF4: "Gulfstream IV", GLF5: "Gulfstream V", GLF6: "Gulfstream G650", C172: "Cessna 172",
  C182: "Cessna 182", PA28: "Piper Cherokee", P28A: "Piper Cherokee", SR22: "Cirrus SR22", BE35: "Beechcraft Bonanza",
  BE40: "Beechjet 400", C25B: "Cessna Citation", C56X: "Cessna Citation Excel", PC12: "Pilatus PC-12", RV12: "Van's RV-12",
  PA31: "Piper Navajo", C82T: "Cessna 182",
};

/** "DAL1423" -> "Delta 1423"; N-numbers stay as they are. */
export function flightName(cs: string): string {
  const m = /^([A-Z]{3})(\d+[A-Z]?)$/.exec(cs);
  if (m && AIRLINES[m[1]]) return `${AIRLINES[m[1]]} ${m[2]}`;
  if (/^[0-9a-f]{6}(-\w+)?$/.test(cs)) return "Unknown flight"; // no callsign broadcast, only the transponder code
  return cs;
}

export const typeName = (t: string) => TYPES[t] ?? (t === "UNKN" ? "Unknown aircraft" : t);
export const ft = (n: number) => `${Math.round(n / 100) * 100 > 0 ? (Math.round(n / 100) * 100).toLocaleString() : 0} ft`;
export const knotsMph = (kt: number) => `${kt} knots (${Math.round(kt * 1.15078)} mph)`;

export function verticalWord(a: AircraftView): string {
  if (a.vs_fpm > 300) return "climbing";
  if (a.vs_fpm < -300) return "descending";
  return "level";
}

/** True for airliners/bizjets (drawn big), false for small planes. */
export function isBig(a: AircraftView): boolean {
  if (a.minor || a.flight_rules === "VFR") return false;
  return !/^(C1[5-8]\d|C2\d\d|PA\d\d|P28A|SR2\d|BE3\d|RV\d+|C82T)$/.test(a.type);
}

/** The suggested instruction in everyday words. */
export function plainSuggestion(s: SuggestionView): string {
  const who = flightName(s.callsign);
  switch (s.action) {
    case "climb": return `Tell ${who} to climb to ${ft(s.value)}`;
    case "descend": return `Tell ${who} to descend to ${ft(s.value)}`;
    case "turn": return `Tell ${who} to turn to heading ${String(Math.round(s.value)).padStart(3, "0")}°`;
    case "speed": return `Tell ${who} to change speed to ${s.value} knots`;
  }
}

export const mmss = (s: number) => (s >= 60 ? `${Math.floor(s / 60)} min ${s % 60 ? `${s % 60} s` : ""}`.trim() : `${s} s`);
