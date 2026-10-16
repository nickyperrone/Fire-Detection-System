import type { RiskEvent } from "../api/client";
import type { Messages } from "../i18n/messages";
import { formatNumber } from "../i18n/text";

/** What the wind does to a fire near the field, from its risk factors (docs/03-rules.md#wind):
 * whether it blows from the fire toward the field, and a rough time of arrival. */
export function windPush(
  t: Messages,
  risk: RiskEvent | undefined,
): { toward: string; arrival: string | null } | null {
  const f = risk?.factors as
    | { wind_toward?: boolean; wind_kmh?: number; arrival_h?: number | null }
    | undefined;
  if (!f?.wind_toward || f.wind_kmh == null) return null;
  return {
    toward: t.fire.windToward(formatNumber(t, f.wind_kmh)),
    arrival: f.arrival_h == null ? null : t.fire.arrival(span(t, f.arrival_h)),
  };
}

/** "~25 min", "~2,4 h", "~5 h": rounder the further off it is. */
export function span(t: Messages, hours: number): string {
  if (hours < 1) return `~${Math.max(5, Math.round((hours * 60) / 5) * 5)} min`;
  return `~${formatNumber(t, hours, hours >= 3 ? 0 : 1)} h`;
}
