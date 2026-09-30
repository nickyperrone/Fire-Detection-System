"use client";

import type { PortfolioEntry } from "@/api/client";
import { formatHectares } from "@/lib/format";

import { FieldAnswers } from "./FieldAnswers";

type Props = {
  entries: PortfolioEntry[];
  allTags: string[];
  activeTags: string[];
  onToggleTag: (tag: string) => void;
  onSelect: (id: number) => void;
};

export function PortfolioPanel({ entries, allTags, activeTags, onToggleTag, onSelect }: Props) {
  const fires = entries.filter((e) => e.fire.severity).length;
  const listed = new Set(entries.map((e) => e.territory_id));

  return (
    <div>
      <h2 className="text-lg font-semibold">
        {fires === 0 ? "No fires near your fields" : `${fires} of ${entries.length} need a look`}
      </h2>
      <p className="text-sm text-muted">
        {entries.filter((e) => e.kind === "FIELD").length} fields ·{" "}
        {entries.filter((e) => e.kind === "SECTION").length} lots, worst first
      </p>

      {allTags.length > 0 && (
        <div className="-mx-4 mt-3 flex gap-2 overflow-x-auto px-4 pb-1">
          {allTags.map((tag) => {
            const active = activeTags.includes(tag);
            return (
              <button
                key={tag}
                onClick={() => onToggleTag(tag)}
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
          return (
            <li key={entry.territory_id} className={underParent ? "ml-4" : ""}>
              <button
                onClick={() => onSelect(entry.territory_id)}
                className="w-full rounded-2xl bg-white/[0.04] p-3 text-left hover:bg-white/[0.07]"
              >
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
