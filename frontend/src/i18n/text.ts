import type { FireAnswer, SprayAnswer } from "@/api/client";

import type { Messages, SprayRule } from "./messages";

const LOCAL_TZ = "America/Argentina/Buenos_Aires";

export function formatAge(
  t: Messages,
  iso: string | null | undefined,
  now: Date = new Date(),
): string {
  if (!iso) return t.age.unknown;
  const minutes = Math.floor(
    (now.getTime() - new Date(iso).getTime()) / 60_000,
  );
  if (minutes < 1) return t.age.justNow;
  if (minutes < 60) return t.age.minutes(minutes);
  if (minutes < 48 * 60) return t.age.hours(Math.floor(minutes / 60));
  return t.age.days(Math.floor(minutes / 1440));
}

export function formatNumber(t: Messages, value: number, digits = 0): string {
  return value.toLocaleString(t.intl, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

export function formatDistance(
  t: Messages,
  meters: number | null | undefined,
): string {
  if (meters === null || meters === undefined) return "";
  if (meters === 0) return t.units.inside;
  return meters < 1000
    ? `${Math.round(meters)} m`
    : `${formatNumber(t, meters / 1000, 1)} km`;
}

export function formatHectares(t: Messages, hectares: number): string {
  return `${formatNumber(t, hectares)} ${t.units.ha}`;
}

export function localTime(t: Messages, iso: string, withDay = false): string {
  return new Intl.DateTimeFormat(t.intl, {
    timeZone: LOCAL_TZ,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    ...(withDay ? { weekday: "short" } : {}),
  }).format(new Date(iso));
}

/** A calendar date ("2026-03-14") as day and month, e.g. "14 mar". */
export function localDate(t: Messages, isoDate: string): string {
  return new Intl.DateTimeFormat(t.intl, {
    timeZone: "UTC",
    day: "numeric",
    month: "short",
  }).format(new Date(`${isoDate}T00:00:00Z`));
}

export function localHourNumber(iso: string): number {
  const hour = new Intl.DateTimeFormat("en-GB", {
    timeZone: LOCAL_TZ,
    hour: "2-digit",
    hourCycle: "h23",
  }).format(new Date(iso));
  return Number(hour);
}

export function direction(
  t: Messages,
  code: string | null | undefined,
): string {
  return code ? (t.directions[code] ?? code) : "";
}

export function fireLabel(t: Messages, fire: FireAnswer): string {
  if (fire.severity) return t.severity[fire.severity];
  if (fire.data_quality === "NO_DATA") return t.fire.noData;
  if (fire.data_quality === "STALE") return t.fire.stale;
  return t.fire.noDetections;
}

export function fireSentence(t: Messages, fire: FireAnswer): string {
  if (!fire.severity) {
    if (fire.data_quality === "NO_DATA") return t.fire.notReadYet;
    if (fire.data_quality === "STALE")
      return t.fire.lastRead(formatAge(t, fire.last_read_at));
    return t.fire.noneWithin;
  }
  const where = fire.distance_m ? direction(t, fire.direction) : "";
  const sentence = t.fire.possibleFire(
    formatDistance(t, fire.distance_m),
    where,
  );
  return fire.other_fires
    ? `${sentence} · ${t.fire.more(fire.other_fires)}`
    : sentence;
}

export function sprayLabel(t: Messages, spray: SprayAnswer): string {
  if (!spray.status) return t.sprayText.noForecast;
  if (spray.data_quality === "STALE") return t.sprayText.stale;
  return t.spray[spray.status];
}

/** One sentence per rule that did not pass, written from its codes and numbers. */
export function ruleSentence(t: Messages, rule: SprayRule): string {
  const name =
    t.rules[
      rule.rule as
        "wind" | "gusts" | "delta_t" | "temperature" | "rain" | "inversion"
    ];
  // The inversion estimate has no value: it is a flag.
  if (rule.rule === "inversion" && rule.status === "CAUTION")
    return t.rules.inversionRisk;
  if (rule.status === "UNKNOWN" || rule.value === null)
    return t.rules.missing(name);

  const withUnit = (n: number) =>
    `${formatNumber(t, n, rule.unit === "°C" ? 1 : 0)} ${rule.unit}`;
  const value = withUnit(rule.value);
  const limit = rule.limit == null ? "" : withUnit(rule.limit);
  const belowLimit = rule.limit != null && rule.value < rule.limit;
  const overOrNear = rule.status === "FAIL" ? t.rules.over : t.rules.near;

  switch (rule.rule) {
    case "wind":
      return belowLimit ? t.rules.calm(value) : overOrNear(name, value, limit);
    case "delta_t":
      if (belowLimit) return t.rules.lowDeltaT(value);
      return rule.status === "FAIL"
        ? t.rules.highDeltaT(value)
        : overOrNear(name, value, limit);
    case "rain":
      return rule.unit === "%"
        ? t.rules.rainChance(value, rule.window_h ?? 2)
        : t.rules.rainAmount(value, rule.window_h ?? 2);
    default:
      return overOrNear(name, value, limit);
  }
}
