import type { Snapshot } from "../api/client";

// A photo opens first when clouds cover less than this share of the field.
const CLEAR_SHARE = 0.1;

/** The photo a field's page opens on: the newest without clouds over the field, or else the
 * newest. */
export function newestClear(snapshots: Snapshot[]): number {
  const clear = snapshots.findLastIndex((s) => s.cloud_share < CLEAR_SHARE);
  return clear >= 0 ? clear : snapshots.length - 1;
}

/** First days of the months after `from`, up to `to` ("2026-05-01", …). */
export function monthStarts(from: string, to: string): string[] {
  const out: string[] = [];
  let [year, month] = from.split("-").map(Number);
  for (;;) {
    month += 1;
    if (month > 12) [year, month] = [year + 1, 1];
    const start = `${year}-${String(month).padStart(2, "0")}-01`;
    if (start > to) return out;
    out.push(start);
  }
}
