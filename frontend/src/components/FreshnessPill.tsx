"use client";

import { useHealth } from "@/api/queries";
import { formatAge } from "@/lib/format";

/** Always visible: when fires were last read, and why not if the source is failing. */
export function FreshnessPill() {
  const { data: health, isError } = useHealth();
  if (isError) return <Pill ok={false}>API unreachable</Pill>;
  if (!health) return null;
  const reads = health.sources
    .filter((s) => s.provider === "firms" && s.last_success_at)
    .map((s) => s.last_success_at!)
    .sort();
  const lastRead = reads.at(-1);
  if (health.fire_data_quality === "NO_DATA") return <Pill ok={false}>No fire data yet</Pill>;
  if (health.fire_data_quality === "STALE") {
    return <Pill ok={false}>Fire data stale · read {formatAge(lastRead)}</Pill>;
  }
  const partial = health.fire_data_quality === "PARTIAL" ? " · some sensors failed" : "";
  return <Pill ok>Fires read {formatAge(lastRead)}{partial}</Pill>;
}

function Pill({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <div className="glass inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs text-slate-200">
      <span className={`size-2 rounded-full ${ok ? "animate-pulse bg-ok" : "bg-unknown"}`} />
      {children}
    </div>
  );
}
