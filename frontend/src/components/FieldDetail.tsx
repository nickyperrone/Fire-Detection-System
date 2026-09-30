"use client";

import type { PortfolioEntry } from "@/api/client";
import { useDeleteTerritory, useRiskEvents, useSprayConditions } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import {
  direction,
  fireSentence,
  formatAge,
  formatDistance,
  formatHectares,
  localTime,
  ruleSentence,
} from "@/i18n/text";
import { fireTone, lightningTone, sprayTone, type Tone } from "@/lib/status";

import { FieldChips, lightningSentence } from "./FieldSummary";
import { BoltIcon, CloseIcon, FlameIcon, SprayIcon } from "./Icons";
import { SprayTimeline } from "./SprayTimeline";

const TONE_TEXT: Record<Tone, string> = {
  bad: "text-bad",
  good: "text-good",
  unknown: "text-slate-300",
};

type Props = { entry: PortfolioEntry; parentName: string | null; onClose: () => void };

export function FieldDetail({ entry, parentName, onClose }: Props) {
  const { t } = useLocale();
  const risks = useRiskEvents(entry.territory_id);
  const hours = useSprayConditions(entry.territory_id);
  const remove = useDeleteTerritory();
  const { fire, spray } = entry;
  const isField = entry.kind === "FIELD";

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-muted">{parentName ? t.detail.lotOf(parentName) : t.detail.field}</p>
          <h2 className="truncate text-xl font-semibold">{entry.name}</h2>
          <p className="text-sm text-muted">
            {formatHectares(t, entry.hectares)}
            {entry.tags.length > 0 && ` · ${entry.tags.join(" · ")}`}
          </p>
          <div className="mt-2">
            <FieldChips entry={entry} />
          </div>
        </div>
        <button onClick={onClose} aria-label={t.detail.close} className="grid size-9 shrink-0 place-items-center rounded-full bg-white/10">
          <CloseIcon className="size-4" />
        </button>
      </header>

      <section>
        <SectionTitle icon={<FlameIcon className="size-4" />}>{t.sections.fire}</SectionTitle>
        <p className={`font-medium ${TONE_TEXT[fireTone(fire)]}`}>{fireSentence(t, fire)}</p>
        {fire.severity ? (
          <div className="mt-2 space-y-0.5 text-sm text-slate-300">
            <p>
              {t.fire.seenBy(fire.sensors.join(", "))} · {t.fire.confidence(t.confidence[fire.confidence ?? ""] ?? "")}
            </p>
            <p>{t.fire.times(formatAge(t, fire.acquired_at), formatAge(t, fire.received_at))}</p>
          </div>
        ) : (
          fire.data_quality !== "NO_DATA" && (
            <p className="mt-1 text-sm text-slate-400">{t.fire.lastRead(formatAge(t, fire.last_read_at))}</p>
          )
        )}
        {(risks.data?.length ?? 0) > 1 && (
          <ul className="mt-2 space-y-1 text-sm text-slate-300">
            {risks.data!.map((r) => (
              <li key={r.id} className="flex justify-between">
                <span>
                  {t.severity[r.severity]} · {formatDistance(t, r.distance_m)} {direction(t, r.direction)}
                </span>
              </li>
            ))}
          </ul>
        )}
        {risks.data?.[0] && (
          <p className="mt-2 text-[11px] text-muted">{t.fire.rulesVersion(risks.data[0].processing_version)}</p>
        )}
      </section>

      <section>
        <SectionTitle icon={<BoltIcon className="size-4" />}>{t.sections.lightning}</SectionTitle>
        <p className={`font-medium ${TONE_TEXT[lightningTone(entry.lightning)]}`}>
          {lightningTone(entry.lightning) === "unknown"
            ? t.lightning.noData
            : lightningSentence(t, entry)}
        </p>
        {entry.lightning.flashes > 0 && (
          <div className="mt-1 space-y-0.5 text-sm text-slate-300">
            <p>{t.lightning.last(formatAge(t, entry.lightning.last_at))}</p>
            <p className="text-slate-400">{t.lightning.why}</p>
          </div>
        )}
      </section>

      <section>
        <SectionTitle icon={<SprayIcon className="size-4" />}>{t.sections.spray}</SectionTitle>
        {spray.status ? (
          <div className="mb-3 space-y-0.5">
            <p className={`font-medium ${TONE_TEXT[sprayTone(spray)]}`}>
              {t.sprayText.now}: {t.spray[spray.status]}
            </p>
            {spray.problems.map((rule) => (
              <p key={rule.rule} className="text-sm text-slate-300">
                {ruleSentence(t, rule)}
              </p>
            ))}
            {spray.status !== "FAVORABLE" && (
              <p className="text-sm text-slate-300">
                {spray.next_favorable
                  ? t.sprayText.nextWindow(
                      `${localTime(t, spray.next_favorable[0], true)}–${localTime(t, spray.next_favorable[1])}`,
                    )
                  : t.sprayText.noWindow}
              </p>
            )}
            {spray.drift_toward && (
              <p className="text-sm text-slate-400">{t.sprayText.driftToward(direction(t, spray.drift_toward))}</p>
            )}
          </div>
        ) : null}
        <SprayTimeline hours={hours.data ?? []} />
        <p className="mt-2 text-[11px] leading-4 text-muted">{t.sprayText.disclaimer}</p>
      </section>

      <section>
        <SectionTitle>{t.sections.unusual}</SectionTitle>
        <p className="text-sm text-slate-400">{t.sections.unusualSoon}</p>
      </section>

      <button
        onClick={() => {
          if (window.confirm(t.detail.confirmDelete(entry.name, isField))) {
            remove.mutate(entry.territory_id, { onSuccess: onClose });
          }
        }}
        className="text-sm text-bad/80 hover:text-bad"
      >
        {isField ? t.detail.deleteField : t.detail.deleteLot}
      </button>
    </div>
  );
}

function SectionTitle({ icon, children }: { icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
      {icon}
      {children}
    </h3>
  );
}
