"use client";

import { useState } from "react";

import type { PortfolioEntry } from "@/api/client";
import { useLocale } from "@/i18n/LocaleProvider";
import { formatHectares } from "@/i18n/text";
import {
  allFine,
  attention,
  hazardTone,
  lotNeedsALook,
  TONE_HEX,
} from "@/lib/status";
import { weatherLine } from "@/lib/weather";

import { FieldChips, headline } from "./FieldSummary";
import { BellOffIcon, CheckIcon, ChevronIcon, StarIcon } from "./Icons";

type Props = {
  entries: PortfolioEntry[];
  /** Fields and lots the user hid: listed apart, at the end, and left out of the summary. */
  hidden: Set<number>;
  allTags: string[];
  tagColors: Map<string, string>;
  activeTags: string[];
  picked: number[];
  onlyPicked: boolean;
  onToggleTag: (tag: string) => void;
  onTogglePick: (id: number) => void;
  onShowOnlyPicked: () => void;
  onShowAll: () => void;
  onClearPicked: () => void;
  onSelect: (id: number) => void;
};

export function PortfolioPanel(props: Props) {
  const { t } = useLocale();
  const { picked, onlyPicked, hidden } = props;
  const entries = props.entries.filter((e) => !hidden.has(e.territory_id));
  const hiddenEntries = props.entries.filter((e) => hidden.has(e.territory_id));
  const fields = entries.filter((e) => e.kind === "FIELD");
  const withFire = fields.filter((e) => e.fire.severity).length;
  const goodToSpray = entries.filter(
    (e) => e.spray.status === "FAVORABLE",
  ).length;
  const unusual = entries.filter((e) => e.anomaly.patches.length > 0).length;

  return (
    <div>
      <h2 className={`text-lg font-semibold ${withFire ? "text-bad" : ""}`}>
        {withFire
          ? t.portfolio.withFire(withFire)
          : t.portfolio.allQuiet(fields.length)}
      </h2>
      <p className="text-sm text-muted">
        {t.portfolio.sprayNow(goodToSpray, entries.length)} ·{" "}
        {t.portfolio.counts(fields.length, entries.length - fields.length)}
        {unusual > 0 && (
          <span className="text-bad"> · {t.portfolio.unusual(unusual)}</span>
        )}
      </p>

      {picked.length > 0 && <SelectionBar {...props} />}

      {!onlyPicked && props.allTags.length > 0 && (
        <div className="no-scrollbar -mx-4 mt-3 flex gap-2 overflow-x-auto px-4 pb-1 [mask-image:linear-gradient(90deg,transparent,#000_16px,#000_calc(100%-32px),transparent)]">
          {props.allTags.map((tag) => {
            const active = props.activeTags.includes(tag);
            return (
              <button
                key={tag}
                onClick={() => props.onToggleTag(tag)}
                aria-pressed={active}
                className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${
                  active
                    ? "border-accent bg-accent/15 text-accent"
                    : "border-line text-slate-300"
                }`}
              >
                <span
                  className="size-2.5 rounded-full"
                  style={{ background: props.tagColors.get(tag) }}
                />
                {tag}
              </button>
            );
          })}
        </div>
      )}

      <EntryList {...props} entries={entries} />
      {hiddenEntries.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm text-muted">
            {t.portfolio.hidden(hiddenEntries.length)}
          </summary>
          <div className="opacity-70">
            <EntryList {...props} entries={hiddenEntries} />
          </div>
        </details>
      )}
    </div>
  );
}

function SelectionBar({
  picked,
  onlyPicked,
  onShowOnlyPicked,
  onShowAll,
  onClearPicked,
}: Props) {
  const { t } = useLocale();
  return (
    <div className="mt-3 flex items-center justify-between gap-2 rounded-2xl bg-accent/10 px-3 py-2 text-sm">
      <span className="font-medium text-accent">
        {onlyPicked
          ? t.portfolio.showingSelected(picked.length)
          : t.portfolio.selected(picked.length)}
      </span>
      <div className="flex gap-1">
        {onlyPicked ? (
          <button
            onClick={onShowAll}
            className="rounded-lg px-2 py-1 text-slate-200"
          >
            {t.portfolio.showAll}
          </button>
        ) : (
          <button
            onClick={onShowOnlyPicked}
            className="rounded-lg bg-accent px-3 py-1 font-semibold text-slate-950"
          >
            {t.portfolio.showOnly}
          </button>
        )}
        <button
          onClick={onClearPicked}
          className="rounded-lg px-2 py-1 text-muted"
        >
          {t.portfolio.clear}
        </button>
      </div>
    </div>
  );
}

const STAGGERED_ROWS = 12;

type Group = { field: PortfolioEntry; lots: PortfolioEntry[]; rank: number };

/** Fields with their lots, the ones that need a look first; a field ranks by its worst lot. */
function groups(entries: PortfolioEntry[]): Group[] {
  const listed = new Set(entries.map((e) => e.territory_id));
  const tops = entries.filter(
    (e) => e.parent_id === null || !listed.has(e.parent_id),
  );
  return tops
    .map((field) => {
      const lots = entries.filter((e) => e.parent_id === field.territory_id);
      const rank = Math.min(...[field, ...lots].map(attention));
      return { field, lots, rank };
    })
    .sort(
      (a, b) =>
        a.rank - b.rank ||
        Number(b.field.priority === "HIGH") -
          Number(a.field.priority === "HIGH"),
    );
}

/** The field's state, the same color it has on the map (docs/01-product.md#field-states). */
function Dot({ entry }: { entry: PortfolioEntry }) {
  return (
    <span
      aria-hidden
      className="size-2 shrink-0 rounded-full"
      style={{ background: TONE_HEX[hazardTone(entry.fire, entry.lightning)] }}
    />
  );
}

function EntryList(props: Props) {
  const { t } = useLocale();
  const [open, setOpen] = useState<Set<number>>(new Set());
  const toggle = (id: number) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <ul className="mt-3 space-y-2">
      {groups(props.entries).map(({ field, lots }, index) => {
        const needLook = lots.filter(lotNeedsALook).length;
        const expanded = open.has(field.territory_id);
        return (
          <li
            key={field.territory_id}
            // A short cascade; rows past the first screen appear without waiting.
            style={{
              animationDelay: `${Math.min(index, STAGGERED_ROWS) * 25}ms`,
            }}
            className={`rise-in overflow-hidden rounded-2xl ${
              props.picked.includes(field.territory_id)
                ? "bg-accent/10 ring-1 ring-accent/50"
                : "bg-white/[0.04]"
            }`}
          >
            <Row {...props} entry={field} />
            {lots.length > 0 && (
              <>
                <button
                  aria-expanded={expanded}
                  aria-label={t.portfolio.showLots(field.name)}
                  onClick={() => toggle(field.territory_id)}
                  className="flex w-full items-center gap-2 border-t border-white/[0.06] px-4 py-2.5 text-left text-xs text-muted hover:bg-white/[0.03] hover:text-slate-200"
                >
                  <ChevronIcon
                    className={`size-3.5 transition-transform ${expanded ? "rotate-90" : ""}`}
                  />
                  {t.portfolio.lots(lots.length)}
                  {needLook > 0 && (
                    <span className="text-bad">
                      · {t.portfolio.lotsNeedLook(needLook)}
                    </span>
                  )}
                </button>
                {expanded && (
                  <ul className="border-t border-white/[0.06]">
                    {lots.map((lot) => (
                      <li key={lot.territory_id}>
                        <Row {...props} entry={lot} compact />
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** One field, or one lot inside its field (`compact`). "All fine" is a quiet line, not chips. */
function Row(props: Props & { entry: PortfolioEntry; compact?: boolean }) {
  const { t } = useLocale();
  const { entry, compact = false } = props;
  const isPicked = props.picked.includes(entry.territory_id);
  const fine = allFine(entry);
  const weather = weatherLine(t, entry.weather);

  return (
    <div className="flex items-stretch">
      <button
        role="checkbox"
        aria-checked={isPicked}
        aria-label={t.portfolio.select(entry.name)}
        onClick={() => props.onTogglePick(entry.territory_id)}
        className="grid w-11 shrink-0 place-items-center"
      >
        <span
          className={`grid size-[18px] place-items-center rounded-md border-[1.5px] ${
            isPicked
              ? "border-accent bg-accent text-slate-950"
              : "border-slate-500"
          }`}
        >
          {isPicked && <CheckIcon className="size-3" />}
        </span>
      </button>
      <button
        onClick={() => props.onSelect(entry.territory_id)}
        className={`min-w-0 flex-1 pr-4 text-left ${compact ? "py-2.5" : "py-3"}`}
      >
        <span className="flex items-center gap-2">
          <Dot entry={entry} />
          <span
            className={`min-w-0 truncate ${compact ? "text-sm" : "font-medium"}`}
          >
            {entry.name}
          </span>
          {entry.priority === "HIGH" && (
            <span title={t.portfolio.highPriority}>
              <StarIcon className="size-3.5 shrink-0 text-accent" />
              <span className="sr-only">{t.portfolio.highPriority}</span>
            </span>
          )}
          {!entry.alerts && (
            <span title={t.portfolio.alertsOff}>
              <BellOffIcon className="size-3.5 shrink-0 text-muted" />
              <span className="sr-only">{t.portfolio.alertsOff}</span>
            </span>
          )}
          <span className="ml-auto shrink-0 text-xs text-muted tabular-nums">
            {formatHectares(t, entry.hectares)}
          </span>
        </span>
        {fine ? (
          !compact && (
            <span className="mt-1 block truncate pl-4 text-xs text-slate-400">
              {t.portfolio.allFine}
              {weather && ` · ${weather}`}
            </span>
          )
        ) : (
          <span className="mt-2 block space-y-1.5 pl-4">
            <FieldChips entry={entry} onlyProblems />
            {!compact && (
              <span className="block truncate text-[13px] text-slate-400">
                {headline(t, entry)}
              </span>
            )}
          </span>
        )}
      </button>
    </div>
  );
}
