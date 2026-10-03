"use client";

import { useState } from "react";

import type { PortfolioEntry } from "@/api/client";
import { useReplaceTags, useSetTagColor, useTags } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import { TONE_HEX } from "@/lib/status";

import { CloseIcon } from "./Icons";

/** A field's tags: remove, add (existing ones suggested) and recolor (docs/01-product.md#tags-and-colors). */
export function TagEditor({ entry }: { entry: PortfolioEntry }) {
  const { t } = useLocale();
  const tags = useTags();
  const replace = useReplaceTags();
  const recolor = useSetTagColor();
  const [draft, setDraft] = useState("");
  const [picking, setPicking] = useState<string | null>(null);
  const byLabel = new Map(
    (tags.data?.tags ?? []).map((tag) => [tag.label, tag]),
  );
  const picked = picking ? byLabel.get(picking) : undefined;
  const save = (next: string[]) =>
    replace.mutate({ id: entry.territory_id, tags: next });
  const listId = `tags-${entry.territory_id}`;

  return (
    <div>
      {entry.tags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {entry.tags.map((label) => (
            <span
              key={label}
              className="flex items-center gap-1.5 rounded-full border border-line py-1 pl-1.5 pr-2 text-xs"
            >
              <button
                aria-label={t.tags.changeColor(label)}
                aria-expanded={picking === label}
                onClick={() => setPicking(picking === label ? null : label)}
                className="size-4 rounded-full"
                style={{
                  background: byLabel.get(label)?.color ?? TONE_HEX.unknown,
                }}
              />
              {label}
              <button
                aria-label={t.tags.remove(label)}
                onClick={() => save(entry.tags.filter((l) => l !== label))}
                className="text-muted hover:text-slate-100"
              >
                <CloseIcon className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      {picked && tags.data && (
        <div
          role="radiogroup"
          aria-label={t.tags.changeColor(picked.label)}
          className="mt-3 flex flex-wrap gap-2"
        >
          {tags.data.palette.map((color) => (
            <button
              key={color}
              role="radio"
              aria-checked={picked.color === color}
              aria-label={color}
              onClick={() => {
                recolor.mutate({ id: picked.id, color });
                setPicking(null);
              }}
              className={`size-7 rounded-full ${
                picked.color === color
                  ? "ring-2 ring-white ring-offset-2 ring-offset-surface"
                  : ""
              }`}
              style={{ background: color }}
            />
          ))}
        </div>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const label = draft.trim();
          if (label && !entry.tags.includes(label))
            save([...entry.tags, label]);
          setDraft("");
        }}
        className="mt-3 flex gap-2"
      >
        <input
          list={listId}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t.tags.addPlaceholder}
          aria-label={t.tags.add}
          className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-surface-2 px-3 text-sm outline-none focus:border-accent"
        />
        <datalist id={listId}>
          {(tags.data?.tags ?? [])
            .filter((tag) => !entry.tags.includes(tag.label))
            .map((tag) => (
              <option key={tag.id} value={tag.label} />
            ))}
        </datalist>
        <button
          type="submit"
          disabled={!draft.trim() || replace.isPending}
          className="h-10 rounded-xl bg-white/10 px-4 text-sm font-medium disabled:opacity-50"
        >
          {t.tags.add}
        </button>
      </form>
    </div>
  );
}
