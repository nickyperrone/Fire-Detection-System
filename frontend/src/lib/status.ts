import type { DataQuality, FireAnswer, Severity, SprayAnswer, SprayStatus } from "../api/client";

/** One color scale for the map, chips and lists (docs/04-frontend.md#layout). */
export type Tone = "critical" | "high" | "watch" | "ok" | "unknown";

export const TONE_HEX: Record<Tone, string> = {
  critical: "#ef4444",
  high: "#f97316",
  watch: "#f5b300",
  ok: "#22c55e",
  unknown: "#6b7280",
};

const SEVERITY_TONE: Record<Severity, Tone> = {
  CRITICAL: "critical",
  VERY_HIGH: "high",
  HIGH: "high",
  WATCH: "watch",
};

const SPRAY_TONE: Record<SprayStatus, Tone> = {
  UNFAVORABLE: "critical",
  CAUTION: "watch",
  FAVORABLE: "ok",
};

const BLIND: DataQuality[] = ["NO_DATA", "STALE"];

export function fireTone(fire: FireAnswer): Tone {
  if (fire.severity) return SEVERITY_TONE[fire.severity];
  // No detections only counts as good news when the sources were actually read.
  return BLIND.includes(fire.data_quality) ? "unknown" : "ok";
}

export function sprayTone(spray: SprayAnswer): Tone {
  if (!spray.status || BLIND.includes(spray.data_quality)) return "unknown";
  return SPRAY_TONE[spray.status];
}

export function sprayStatusTone(status: SprayStatus): Tone {
  return SPRAY_TONE[status];
}
