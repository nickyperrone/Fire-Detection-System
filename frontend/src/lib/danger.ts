import type { PortfolioEntry, Severity } from "../api/client";

const SEVERITY_RANK: Record<Severity, number> = {
  WATCH: 1,
  HIGH: 2,
  VERY_HIGH: 3,
  CRITICAL: 4,
};

/** What is threatening a field right now: how close the nearest fire is, and lightning. */
export type Danger = { fire: number; lightning: boolean };

export function dangerOf(entry: PortfolioEntry): Danger {
  return {
    fire: entry.fire.severity ? SEVERITY_RANK[entry.fire.severity] : 0,
    lightning: entry.lightning.flashes > 0,
  };
}

/**
 * Whether danger started or got worse since `before` (docs/01-product.md#settings-per-field):
 * a fire where there was none or closer than before, or lightning where there was none.
 * Without `before` the field was just loaded, and what was already there is not news.
 */
export function dangerGrew(before: Danger | undefined, now: Danger): boolean {
  if (!before) return false;
  return now.fire > before.fire || (now.lightning && !before.lightning);
}
