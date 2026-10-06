"use client";

import type { PortfolioEntry } from "@/api/client";
import {
  useDeleteTerritory,
  useRiskEvents,
  useSprayConditions,
} from "@/api/queries";
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
import {
  fireTone,
  hazardTone,
  lotNeedsALook,
  lightningTone,
  sprayTone,
  type Tone,
  TONE_HEX,
} from "@/lib/status";

import type { FieldTab } from "@/lib/useUrlState";
import { FIELD_TABS } from "@/lib/useUrlState";

import { AnomalySection } from "./Anomalies";
import { Breadcrumbs } from "./Breadcrumbs";
import { FieldPhotos } from "./FieldPhotos";
import { FieldSettings } from "./FieldSettings";
import { FieldChips, headline, lightningSentence } from "./FieldSummary";
import { FireHistory } from "./FireHistory";
import { ForecastSection } from "./ForecastSection";
import {
  BoltIcon,
  ChevronIcon,
  CloseIcon,
  FlameIcon,
  ForecastIcon,
  HistoryIcon,
  PatchIcon,
  PencilPlusIcon,
  SprayIcon,
  WindIcon,
} from "./Icons";
import { SprayTimeline } from "./SprayTimeline";
import { WeatherSection } from "./Weather";
import { TagEditor } from "./TagEditor";

const TONE_TEXT: Record<Tone, string> = {
  bad: "text-bad",
  good: "text-good",
  unknown: "text-slate-300",
};

type Props = {
  entry: PortfolioEntry;
  /** The lot's field; null on a field's own page. */
  parent: PortfolioEntry | null;
  /** A field's lots, in the order the list shows them. */
  lots: PortfolioEntry[];
  tab: FieldTab;
  onTab: (tab: FieldTab) => void;
  /** Opens another field or lot, or the list with null. */
  onOpen: (id: number | null) => void;
  onEditOutline: () => void;
  /** The box to add a tag is open, e.g. from "+ Etiqueta" in the map legend. */
  addingTag: boolean;
  onAddingTagChange: (adding: boolean) => void;
};

/** A field's or lot's own page (docs/12-field-page.md): where it sits, its answers, its photos,
 * its history and its settings. */
export function FieldPage({
  entry,
  parent,
  lots,
  tab,
  onTab,
  onOpen,
  onEditOutline,
  addingTag,
  onAddingTagChange,
}: Props) {
  const { t } = useLocale();

  return (
    <div>
      <header className="sticky top-0 z-10 -mx-4 border-b border-white/[0.06] bg-[rgb(17_21_28/0.97)] px-4 pb-3 pt-1 backdrop-blur-xl md:-top-4 md:-mt-4 md:pt-4">
        <div className="flex items-center justify-between gap-3">
          <Breadcrumbs
            items={[
              { label: t.page.root, onClick: () => onOpen(null) },
              ...(parent
                ? [
                    {
                      label: parent.name,
                      onClick: () => onOpen(parent.territory_id),
                    },
                  ]
                : []),
            ]}
          />
          <button
            onClick={() => onOpen(null)}
            aria-label={t.detail.close}
            className="grid size-10 shrink-0 place-items-center rounded-full bg-white/[0.07] text-slate-300 hover:bg-white/15 hover:text-white md:size-8"
          >
            <CloseIcon className="size-4" />
          </button>
        </div>
        <h2 className="mt-3 truncate text-2xl font-semibold tracking-tight">
          {entry.name}
        </h2>
        <p className="mt-0.5 text-sm text-muted tabular-nums">
          {formatHectares(t, entry.hectares)}
        </p>
        <div className="mt-3">
          <FieldChips entry={entry} />
        </div>
        <div className="mt-3">
          <TagEditor
            key={entry.territory_id}
            entry={entry}
            adding={addingTag}
            onAddingChange={onAddingTagChange}
          />
        </div>
        <Tabs tab={tab} onTab={onTab} />
      </header>

      <div key={tab} className="rise-in space-y-6 pt-4">
        {tab === "now" && <Now entry={entry} lots={lots} onOpen={onOpen} />}
        {tab === "photos" && <FieldPhotos territoryId={entry.territory_id} />}
        {tab === "history" && (
          <section>
            <SectionTitle icon={<HistoryIcon className="size-4" />}>
              {t.sections.history}
            </SectionTitle>
            <FireHistory territoryId={entry.territory_id} />
          </section>
        )}
        {tab === "settings" && (
          <Settings
            entry={entry}
            lots={lots}
            onOpen={onOpen}
            onEditOutline={onEditOutline}
          />
        )}
      </div>
    </div>
  );
}

/** A segmented control whose white pill slides to the open tab. */
function Tabs({
  tab,
  onTab,
}: {
  tab: FieldTab;
  onTab: (tab: FieldTab) => void;
}) {
  const { t } = useLocale();
  const index = FIELD_TABS.indexOf(tab);
  return (
    <div
      role="tablist"
      aria-label={t.page.tabsLabel}
      className="relative mt-4 grid grid-cols-4 rounded-full bg-white/[0.07] p-1"
    >
      <span
        aria-hidden
        className="absolute inset-y-1 left-1 w-[calc((100%-0.5rem)/4)] rounded-full bg-white shadow-[0_2px_8px_rgb(0_0_0/0.3)] transition-transform duration-300 ease-[cubic-bezier(0.34,1.3,0.64,1)]"
        style={{ transform: `translateX(${index * 100}%)` }}
      />
      {FIELD_TABS.map((option) => (
        <button
          key={option}
          role="tab"
          aria-selected={tab === option}
          onClick={() => onTab(option)}
          className={`relative z-10 rounded-full py-2 text-[13px] font-medium transition-colors ${
            tab === option
              ? "text-slate-950"
              : "text-slate-300 hover:text-white"
          }`}
        >
          {t.page.tabs[option]}
        </button>
      ))}
    </div>
  );
}

/** Today's answers: fire, spraying, weather, lightning, unusual patches and the fire forecast. */
function Now({
  entry,
  lots,
  onOpen,
}: {
  entry: PortfolioEntry;
  lots: PortfolioEntry[];
  onOpen: (id: number | null) => void;
}) {
  const { t } = useLocale();
  const risks = useRiskEvents(entry.territory_id);
  const hours = useSprayConditions(entry.territory_id);
  const { fire, spray } = entry;

  return (
    <>
      {lots.length > 0 && (
        <section>
          <SectionTitle>{t.page.lots}</SectionTitle>
          <LotList lots={lots} onOpen={onOpen} />
        </section>
      )}

      <section>
        <SectionTitle icon={<FlameIcon className="size-4" />}>
          {t.sections.fire}
        </SectionTitle>
        <p className={`font-medium ${TONE_TEXT[fireTone(fire)]}`}>
          {fireSentence(t, fire)}
        </p>
        {fire.severity ? (
          <div className="mt-2 space-y-0.5 text-sm text-slate-300">
            <p>
              {t.fire.seenBy(fire.sensors.join(", "))} ·{" "}
              {t.fire.confidence(t.confidence[fire.confidence ?? ""] ?? "")}
            </p>
            <p>
              {t.fire.times(
                formatAge(t, fire.acquired_at),
                formatAge(t, fire.received_at),
              )}
            </p>
          </div>
        ) : (
          // With NO_DATA or STALE the sentence above already says when satellites were read.
          !["NO_DATA", "STALE"].includes(fire.data_quality) && (
            <p className="mt-1 text-sm text-slate-400">
              {t.fire.lastRead(formatAge(t, fire.last_read_at))}
            </p>
          )
        )}
        {(risks.data?.length ?? 0) > 1 && (
          <ul className="mt-2 space-y-1 text-sm text-slate-300">
            {risks.data!.map((r) => (
              <li key={r.id}>
                {t.severity[r.severity]} · {formatDistance(t, r.distance_m)}{" "}
                {direction(t, r.direction)}
              </li>
            ))}
          </ul>
        )}
        {risks.data?.[0] && (
          <p className="mt-2 text-[11px] text-muted">
            {t.fire.rulesVersion(risks.data[0].processing_version)}
          </p>
        )}
      </section>

      <section>
        <SectionTitle icon={<SprayIcon className="size-4" />}>
          {t.sections.spray}
        </SectionTitle>
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
              <p className="text-sm text-slate-400">
                {t.sprayText.driftToward(direction(t, spray.drift_toward))}
              </p>
            )}
          </div>
        ) : null}
        <SprayTimeline hours={hours.data ?? []} />
        <p className="mt-2 text-[11px] leading-4 text-muted">
          {t.sprayText.disclaimer}
        </p>
      </section>

      <section>
        <SectionTitle icon={<WindIcon className="size-4" />}>
          {t.weather.title}
        </SectionTitle>
        <WeatherSection weather={entry.weather} hours={hours.data ?? []} />
      </section>

      <section>
        <SectionTitle icon={<BoltIcon className="size-4" />}>
          {t.sections.lightning}
        </SectionTitle>
        <p
          className={`font-medium ${TONE_TEXT[lightningTone(entry.lightning)]}`}
        >
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
        <SectionTitle icon={<PatchIcon className="size-4" />}>
          {t.sections.unusual}
        </SectionTitle>
        <AnomalySection anomaly={entry.anomaly} />
      </section>

      <section>
        <SectionTitle icon={<ForecastIcon className="size-4" />}>
          {t.forecast.title}
        </SectionTitle>
        <ForecastSection forecast={entry.forecast} />
      </section>
    </>
  );
}

/** Alerts and priority, tags, lots, the outline and deleting. */
function Settings({
  entry,
  lots,
  onOpen,
  onEditOutline,
}: {
  entry: PortfolioEntry;
  lots: PortfolioEntry[];
  onOpen: (id: number | null) => void;
  onEditOutline: () => void;
}) {
  const { t } = useLocale();
  const remove = useDeleteTerritory();
  const isField = entry.kind === "FIELD";

  return (
    <>
      <FieldSettings entry={entry} />

      {isField && (
        <section>
          <SectionTitle>{t.page.lots}</SectionTitle>
          {lots.length === 0 ? (
            <p className="text-sm text-slate-300">{t.page.noLots}</p>
          ) : (
            <LotList lots={lots} onOpen={onOpen} />
          )}
        </section>
      )}

      <section>
        <SectionTitle>{t.page.outline}</SectionTitle>
        <button
          onClick={onEditOutline}
          className="flex items-center gap-1.5 text-sm font-medium text-accent"
        >
          <PencilPlusIcon className="size-4" />
          {t.detail.editOutline}
        </button>
      </section>

      <section>
        <SectionTitle>{t.page.danger}</SectionTitle>
        <button
          onClick={() => {
            if (window.confirm(t.detail.confirmDelete(entry.name, isField))) {
              remove.mutate(entry.territory_id, {
                onSuccess: () => onOpen(null),
              });
            }
          }}
          className="text-sm text-bad/80 hover:text-bad"
        >
          {isField ? t.detail.deleteField : t.detail.deleteLot}
        </button>
      </section>
    </>
  );
}

/** A field's lots, each opening its own page, with a dot that says whether it needs a look. */
function LotList({
  lots,
  onOpen,
}: {
  lots: PortfolioEntry[];
  onOpen: (id: number | null) => void;
}) {
  const { t } = useLocale();
  return (
    <ul className="divide-y divide-white/[0.06] overflow-hidden rounded-2xl bg-white/[0.04]">
      {lots.map((lot) => (
        <li key={lot.territory_id}>
          <button
            onClick={() => onOpen(lot.territory_id)}
            className="flex min-h-11 w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-white/5"
          >
            <span
              aria-hidden
              className="size-2 shrink-0 rounded-full"
              style={{
                background: TONE_HEX[hazardTone(lot.fire, lot.lightning)],
              }}
            />
            <span className="min-w-0 flex-1 truncate text-sm font-medium">
              {lot.name}
            </span>
            {lotNeedsALook(lot) && (
              <span className="truncate text-xs text-bad">
                {headline(t, lot)}
              </span>
            )}
            <span className="shrink-0 text-xs text-muted tabular-nums">
              {formatHectares(t, lot.hectares)}
            </span>
            <ChevronIcon className="size-4 shrink-0 text-muted" />
          </button>
        </li>
      ))}
    </ul>
  );
}

function SectionTitle({
  icon,
  children,
}: {
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
      {icon}
      {children}
    </h3>
  );
}
