import type {
  DataQuality,
  FireAnswer,
  LightningAnswer,
  PortfolioEntry,
  SprayAnswer,
  SprayStatus,
} from "../api/client";

/**
 * Two colors for every status (docs/06-goes.md#colors): red when something is wrong, green when
 * all is fine; gray only when there is no data to say either. Severity goes in the text.
 */
export type Tone = "bad" | "good" | "unknown";

export const TONE_HEX: Record<Tone, string> = {
  bad: "#ef4444",
  good: "#22c55e",
  unknown: "#6b7280",
};

const BLIND: DataQuality[] = ["NO_DATA", "STALE"];

export function fireTone(fire: FireAnswer): Tone {
  if (fire.severity) return "bad";
  // No detections only counts as good news when the sources were actually read.
  return BLIND.includes(fire.data_quality) ? "unknown" : "good";
}

export function sprayStatusTone(status: SprayStatus): Tone {
  // Caution is red too: the user asked for one rule, not a third color.
  return status === "FAVORABLE" ? "good" : "bad";
}

export function sprayTone(spray: SprayAnswer): Tone {
  if (!spray.status || BLIND.includes(spray.data_quality)) return "unknown";
  return sprayStatusTone(spray.status);
}

export function lightningTone(lightning: LightningAnswer): Tone {
  if (lightning.flashes > 0) return "bad";
  return BLIND.includes(lightning.data_quality) ? "unknown" : "good";
}

/** Low risk is green; from moderate up it is red, and the band name says how high. */
export function forecastTone(
  band: string | undefined,
  dataQuality: DataQuality,
): Tone {
  if (!band || dataQuality === "NO_DATA") return "unknown";
  return band === "LOW" ? "good" : "bad";
}

/**
 * The field's color on the map: hazards only (fire, lightning). Spraying is often "caution" for
 * hours; if it colored the map, a real fire would no longer stand out. It has its own chip.
 */
export function hazardTone(fire: FireAnswer, lightning: LightningAnswer): Tone {
  const tones = [fireTone(fire), lightningTone(lightning)];
  if (tones.includes("bad")) return "bad";
  return tones.includes("unknown") ? "unknown" : "good";
}

/**
 * How soon a field needs a look, most urgent first (docs/12-field-page.md#the-list): a fire, then
 * lightning, then an unusual patch, then no spraying now, then nothing to see.
 */
export function attention(entry: PortfolioEntry): number {
  if (fireTone(entry.fire) === "bad") return 0;
  if (lightningTone(entry.lightning) === "bad") return 1;
  if (entry.anomaly.patches.length > 0) return 2;
  if (sprayTone(entry.spray) === "bad") return 3;
  return 4;
}

/** Nothing to report: no chip needs to be shown. */
export function allFine(entry: PortfolioEntry): boolean {
  return (
    attention(entry) === 4 &&
    fireTone(entry.fire) === "good" &&
    sprayTone(entry.spray) === "good" &&
    !["HIGH", "VERY_HIGH"].includes(entry.forecast.days[0]?.band ?? "")
  );
}

/**
 * A lot needs its own look: a fire, lightning or an unusual patch. Spraying is left out: the
 * weather of a lot is its field's, and the field already says it.
 */
export function lotNeedsALook(lot: PortfolioEntry): boolean {
  return attention(lot) <= 2;
}
