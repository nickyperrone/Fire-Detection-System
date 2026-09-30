"use client";

import type { PortfolioEntry } from "@/api/client";
import { useDeleteTerritory, useRiskEvents, useSprayConditions } from "@/api/queries";
import { formatAge, formatHectares, formatKm } from "@/lib/format";

import { FieldAnswers } from "./FieldAnswers";
import { SprayTimeline } from "./SprayTimeline";

type Props = { entry: PortfolioEntry; parentName: string | null; onClose: () => void };

export function FieldDetail({ entry, parentName, onClose }: Props) {
  const risks = useRiskEvents(entry.territory_id);
  const spray = useSprayConditions(entry.territory_id);
  const remove = useDeleteTerritory();
  const { fire } = entry;

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-muted">{parentName ? `${parentName} · lot` : "Field"}</p>
          <h2 className="truncate text-xl font-semibold">{entry.name}</h2>
          <p className="text-sm text-muted">
            {formatHectares(entry.hectares)}
            {entry.tags.length > 0 && ` · ${entry.tags.join(" · ")}`}
          </p>
        </div>
        <button onClick={onClose} aria-label="Close" className="rounded-full bg-white/10 px-3 py-1 text-sm">
          ✕
        </button>
      </header>

      <FieldAnswers entry={entry} />

      <section>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">Fire</h3>
        {fire.severity ? (
          <div className="rounded-xl bg-white/5 p-3 text-sm leading-6">
            <p>
              Possible fire {formatKm(fire.distance_m)} {fire.distance_m ? fire.direction : ""} ·{" "}
              {fire.confidence} confidence
            </p>
            <p className="text-slate-300">Seen by {fire.sensors.join(", ")}</p>
            <p className="text-slate-300">
              Satellite pass {formatAge(fire.acquired_at)} · received {formatAge(fire.received_at)}
            </p>
          </div>
        ) : (
          <p className="text-sm text-slate-300">
            {fire.data_quality === "NO_DATA"
              ? "No fire data: FIRMS has not been read yet."
              : `No detections within 10 km. Fires last read ${formatAge(fire.last_read_at)}.`}
          </p>
        )}
        {(risks.data?.length ?? 0) > 1 && (
          <ul className="mt-2 space-y-1 text-sm text-slate-300">
            {risks.data!.map((r) => (
              <li key={r.id} className="flex justify-between">
                <span>
                  {r.severity.replace("_", " ")} · {formatKm(r.distance_m)} {r.direction}
                </span>
                <span className="text-xs text-muted">{r.status.toLowerCase()}</span>
              </li>
            ))}
          </ul>
        )}
        {risks.data?.[0] && (
          <p className="mt-2 text-[11px] text-muted">Rules version {risks.data[0].processing_version}</p>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
          Spraying, next 48 h
        </h3>
        <SprayTimeline hours={spray.data ?? []} />
        {entry.spray.drift_toward && (
          <p className="mt-2 text-sm text-slate-300">Now drift goes toward the {entry.spray.drift_toward} side.</p>
        )}
        <p className="mt-2 text-[11px] leading-4 text-muted">
          Decision support with the default profile. Check the product label and your equipment.
        </p>
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">Something weird</h3>
        <p className="text-sm text-slate-300">
          Vegetation, water and burn scar changes from Sentinel-2 are not available yet.
        </p>
      </section>

      <button
        onClick={() => {
          if (window.confirm(`Delete ${entry.name}${entry.kind === "FIELD" ? " and its lots" : ""}?`)) {
            remove.mutate(entry.territory_id, { onSuccess: onClose });
          }
        }}
        className="text-sm text-critical/80 hover:text-critical"
      >
        Delete {entry.kind === "FIELD" ? "field" : "lot"}
      </button>
    </div>
  );
}
