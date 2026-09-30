"use client";

import type { PortfolioEntry } from "@/api/client";
import { useLocale } from "@/i18n/LocaleProvider";
import { formatHectares } from "@/i18n/text";

import { FieldChips, headline } from "./FieldSummary";
import { CheckIcon } from "./Icons";

type Props = {
  entries: PortfolioEntry[];
  allTags: string[];
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
  const { entries, picked, onlyPicked } = props;
  const fields = entries.filter((e) => e.kind === "FIELD");
  const withFire = fields.filter((e) => e.fire.severity).length;
  const goodToSpray = entries.filter((e) => e.spray.status === "FAVORABLE").length;
  const listed = new Set(entries.map((e) => e.territory_id));

  return (
    <div>
      <h2 className={`text-lg font-semibold ${withFire ? "text-bad" : ""}`}>
        {withFire ? t.portfolio.withFire(withFire) : t.portfolio.allQuiet(fields.length)}
      </h2>
      <p className="text-sm text-muted">
        {t.portfolio.sprayNow(goodToSpray, entries.length)} ·{" "}
        {t.portfolio.counts(fields.length, entries.length - fields.length)}
      </p>

      {picked.length > 0 && <SelectionBar {...props} />}

      {!onlyPicked && props.allTags.length > 0 && (
        <div className="no-scrollbar -mx-4 mt-3 flex gap-2 overflow-x-auto px-4 pb-1">
          {props.allTags.map((tag) => {
            const active = props.activeTags.includes(tag);
            return (
              <button
                key={tag}
                onClick={() => props.onToggleTag(tag)}
                aria-pressed={active}
                className={`shrink-0 rounded-full border px-3 py-1 text-xs ${
                  active ? "border-accent bg-accent/15 text-accent" : "border-line text-slate-300"
                }`}
              >
                {tag}
              </button>
            );
          })}
        </div>
      )}

      <ul className="mt-3 space-y-2">
        {entries.map((entry) => {
          const isLot = entry.parent_id !== null && listed.has(entry.parent_id);
          const isPicked = picked.includes(entry.territory_id);
          return (
            <li
              key={entry.territory_id}
              className={`flex items-stretch rounded-2xl ${isLot ? "ml-5" : ""} ${
                isPicked ? "bg-accent/10 ring-1 ring-accent/50" : "bg-white/[0.04]"
              }`}
            >
              <button
                role="checkbox"
                aria-checked={isPicked}
                aria-label={t.portfolio.select(entry.name)}
                onClick={() => props.onTogglePick(entry.territory_id)}
                className="grid w-11 shrink-0 place-items-center"
              >
                <span
                  className={`grid size-5 place-items-center rounded-full border-2 ${
                    isPicked ? "border-accent bg-accent text-slate-950" : "border-slate-500"
                  }`}
                >
                  {isPicked && <CheckIcon className="size-3" />}
                </span>
              </button>
              <button
                onClick={() => props.onSelect(entry.territory_id)}
                className="min-w-0 flex-1 py-3 pr-3 text-left"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate font-medium">{entry.name}</span>
                  <span className="shrink-0 text-xs text-muted">{formatHectares(t, entry.hectares)}</span>
                </div>
                <div className="mt-1.5">
                  <FieldChips entry={entry} />
                </div>
                <p className="mt-1.5 truncate text-[13px] text-slate-400">{headline(t, entry)}</p>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function SelectionBar({ picked, onlyPicked, onShowOnlyPicked, onShowAll, onClearPicked }: Props) {
  const { t } = useLocale();
  return (
    <div className="mt-3 flex items-center justify-between gap-2 rounded-2xl bg-accent/10 px-3 py-2 text-sm">
      <span className="font-medium text-accent">
        {onlyPicked ? t.portfolio.showingSelected(picked.length) : t.portfolio.selected(picked.length)}
      </span>
      <div className="flex gap-1">
        {onlyPicked ? (
          <button onClick={onShowAll} className="rounded-lg px-2 py-1 text-slate-200">
            {t.portfolio.showAll}
          </button>
        ) : (
          <button onClick={onShowOnlyPicked} className="rounded-lg bg-accent px-3 py-1 font-semibold text-slate-950">
            {t.portfolio.showOnly}
          </button>
        )}
        <button onClick={onClearPicked} className="rounded-lg px-2 py-1 text-muted">
          {t.portfolio.clear}
        </button>
      </div>
    </div>
  );
}
