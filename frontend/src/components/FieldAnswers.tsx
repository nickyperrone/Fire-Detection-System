import type { PortfolioEntry } from "@/api/client";
import { formatAge, formatKm, localTime } from "@/lib/format";
import { fireLabel, fireTone, sprayLabel, sprayTone } from "@/lib/status";

import { StatusChip } from "./StatusChip";

function fireDetail(entry: PortfolioEntry): string {
  const { fire } = entry;
  if (!fire.severity) {
    if (fire.data_quality === "NO_DATA") return "FIRMS has not been read yet";
    if (fire.data_quality === "STALE") return `last read ${formatAge(fire.last_read_at)}`;
    return "none within 10 km";
  }
  const where = `${formatKm(fire.distance_m)} ${fire.distance_m ? (fire.direction ?? "") : ""}`.trim();
  const more = fire.other_fires ? ` · +${fire.other_fires} more` : "";
  return `Possible fire ${where}${more}`;
}

function sprayDetail(entry: PortfolioEntry): string {
  const { spray } = entry;
  if (!spray.status) return "no forecast yet";
  if (spray.status === "FAVORABLE") return "all rules pass";
  const window = spray.next_favorable;
  const next = window ? `next ok ${localTime(window[0], true)}` : "no ok window in 48 h";
  return `${spray.reasons[0] ?? ""} · ${next}`;
}

/** The three answers for one field or section, in the same order everywhere. */
export function FieldAnswers({ entry, compact = false }: { entry: PortfolioEntry; compact?: boolean }) {
  const rows = [
    { label: "Fire", chip: <StatusChip tone={fireTone(entry.fire)}>{fireLabel(entry.fire)}</StatusChip>, detail: fireDetail(entry) },
    { label: "Spray", chip: <StatusChip tone={sprayTone(entry.spray)}>{sprayLabel(entry.spray)}</StatusChip>, detail: sprayDetail(entry) },
    { label: "Weird", chip: <StatusChip tone="unknown">No data</StatusChip>, detail: entry.anomaly.message },
  ];
  return (
    <dl className={compact ? "space-y-1" : "space-y-2"}>
      {rows.map((row) => (
        <div key={row.label} className="grid grid-cols-[3.25rem_auto_1fr] items-center gap-2">
          <dt className="text-xs uppercase tracking-wide text-muted">{row.label}</dt>
          <dd>{row.chip}</dd>
          <dd className="truncate text-sm text-slate-300">{row.detail}</dd>
        </div>
      ))}
    </dl>
  );
}
