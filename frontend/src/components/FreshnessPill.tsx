"use client";

import { useHealth } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import { formatAge } from "@/i18n/text";

import { SatelliteIcon } from "./Icons";

/** Always visible: the newest satellite pass we processed, and when we last checked. */
export function FreshnessPill() {
  const { t } = useLocale();
  const { data: health, isError } = useHealth();
  if (isError) return <Pill ok={false}>{t.freshness.apiDown}</Pill>;
  if (!health) return null;
  const checks = health.sources
    .filter((s) => s.provider === "firms" && s.last_run_at)
    .map((s) => s.last_run_at!)
    .sort();
  const checked = formatAge(t, checks.at(-1));
  const pass = health.latest_pass;
  if (health.fire_data_quality === "NO_DATA" || !pass) return <Pill ok={false}>{t.freshness.noData}</Pill>;
  if (health.fire_data_quality === "STALE") return <Pill ok={false}>{t.freshness.stale(checked)}</Pill>;
  const partial = health.fire_data_quality === "PARTIAL" ? ` · ${t.freshness.partial}` : "";
  return (
    <Pill ok>
      {t.freshness.lastPass(`${pass.sensor} ${pass.satellite}`, formatAge(t, pass.acquired_at))}
      <span className="text-muted"> · {t.freshness.checked(checked)}{partial}</span>
    </Pill>
  );
}

function Pill({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <div className="glass inline-flex max-w-full items-center gap-2 rounded-full px-3 py-1.5 text-xs text-slate-200">
      <SatelliteIcon className={`size-3.5 shrink-0 ${ok ? "text-good" : "text-unknown"}`} />
      <span className="truncate">{children}</span>
    </div>
  );
}
