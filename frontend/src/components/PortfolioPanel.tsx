"use client";

import type { PortfolioEntry } from "@/api/client";
import { formatHectares } from "@/lib/format";

import { FieldAnswers } from "./FieldAnswers";

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
  const { entries, picked, onlyPicked } = props;
  const fires = entries.filter((e) => e.fire.severity).length;
  const listed = new Set(entries.map((e) => e.territory_id));
  const fieldCount = entries.filter((e) => e.kind === "FIELD").length;

  return (
    <div>
      <h2 className="text-lg font-semibold">
        {fires === 0 ? "No fires near these fields" : `${fires} of ${entries.length} need a look`}
      </h2>
      <p className="text-sm text-muted">
        {fieldCount} fields · {entries.length - fieldCount} lots, worst first
      </p>

      {picked.length > 0 && <SelectionBar {...props} />}

      {!onlyPicked && props.allTags.length > 0 && (
        <div className="-mx-4 mt-3 flex gap-2 overflow-x-auto px-4 pb-1">
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
          const underParent = entry.parent_id !== null && listed.has(entry.parent_id);
          const isPicked = picked.includes(entry.territory_id);
          return (
            <li
              key={entry.territory_id}
              className={`flex items-stretch gap-2 rounded-2xl p-3 ${underParent ? "ml-4" : ""} ${
                isPicked ? "bg-accent/10 ring-1 ring-accent/50" : "bg-white/[0.04]"
              }`}
            >
              <button
                role="checkbox"
                aria-checked={isPicked}
                aria-label={`Select ${entry.name}`}
                onClick={() => props.onTogglePick(entry.territory_id)}
                className="-my-3 -ml-3 grid w-11 shrink-0 place-items-center"
              >
                <span
                  className={`grid size-5 place-items-center rounded-full border-2 text-[11px] font-bold ${
                    isPicked ? "border-accent bg-accent text-slate-950" : "border-slate-500"
                  }`}
                >
                  {isPicked ? "✓" : ""}
                </span>
              </button>
              <button onClick={() => props.onSelect(entry.territory_id)} className="min-w-0 flex-1 text-left">
                <div className="mb-2 flex items-baseline justify-between gap-2">
                  <span className="truncate font-medium">{entry.name}</span>
                  <span className="shrink-0 text-xs text-muted">{formatHectares(entry.hectares)}</span>
                </div>
                <FieldAnswers entry={entry} compact />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function SelectionBar({ picked, onlyPicked, onShowOnlyPicked, onShowAll, onClearPicked }: Props) {
  return (
    <div className="mt-3 flex items-center justify-between gap-2 rounded-2xl bg-accent/10 px-3 py-2 text-sm">
      <span className="font-medium text-accent">
        {onlyPicked ? `Showing ${picked.length} selected` : `${picked.length} selected`}
      </span>
      <div className="flex gap-1">
        {onlyPicked ? (
          <button onClick={onShowAll} className="rounded-lg px-2 py-1 text-slate-200">
            Show all
          </button>
        ) : (
          <button onClick={onShowOnlyPicked} className="rounded-lg bg-accent px-3 py-1 font-semibold text-slate-950">
            Show only these
          </button>
        )}
        <button onClick={onClearPicked} className="rounded-lg px-2 py-1 text-muted">
          Clear
        </button>
      </div>
    </div>
  );
}
