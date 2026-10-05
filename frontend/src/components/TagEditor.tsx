"use client";

import { useEffect, useRef, useState } from "react";

import type { PortfolioEntry } from "@/api/client";
import { useReplaceTags, useSetTagColor, useTags } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import { TONE_HEX } from "@/lib/status";

import { CloseIcon, PlusIcon } from "./Icons";

type Props = {
  entry: PortfolioEntry;
  /** Opens the box to add a tag, e.g. from "+ Etiqueta" in the map legend. */
  adding?: boolean;
  onAddingChange?: (adding: boolean) => void;
};

/** A field's tags as chips, then "+ Etiqueta": remove one with its ×, recolor it from its dot,
 * add one by typing or tapping a tag already used (docs/01-product.md#tags-and-colors). */
export function TagEditor({ entry, adding = false, onAddingChange }: Props) {
  const { t } = useLocale();
  const tags = useTags();
  const replace = useReplaceTags();
  const recolor = useSetTagColor();
  const [ownAdding, setOwnAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const [picking, setPicking] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const open = adding || ownAdding;
  const setOpen = (next: boolean) => {
    setOwnAdding(next);
    onAddingChange?.(next);
  };

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  const byLabel = new Map(
    (tags.data?.tags ?? []).map((tag) => [tag.label, tag]),
  );
  const picked = picking ? byLabel.get(picking) : undefined;
  const save = (next: string[]) =>
    replace.mutate({ id: entry.territory_id, tags: next });
  const add = (label: string) => {
    const clean = label.trim();
    if (clean && !entry.tags.includes(clean)) save([...entry.tags, clean]);
    setDraft("");
  };
  const query = draft.trim().toLowerCase();
  const suggestions = (tags.data?.tags ?? []).filter(
    (tag) =>
      !entry.tags.includes(tag.label) &&
      tag.label.toLowerCase().includes(query),
  );

  return (
    <div>
      <div className="flex flex-wrap items-center gap-1.5">
        {entry.tags.map((label) => (
          <span
            key={label}
            className="flex h-8 items-center gap-1.5 rounded-full bg-white/[0.07] pl-1 pr-1 text-xs text-slate-200"
          >
            <button
              aria-label={t.tags.changeColor(label)}
              aria-expanded={picking === label}
              onClick={() => setPicking(picking === label ? null : label)}
              className="grid size-6 place-items-center"
            >
              <span
                className="size-3 rounded-full"
                style={{
                  background: byLabel.get(label)?.color ?? TONE_HEX.unknown,
                }}
              />
            </button>
            {label}
            <button
              aria-label={t.tags.remove(label)}
              onClick={() => save(entry.tags.filter((l) => l !== label))}
              className="grid size-6 place-items-center rounded-full text-muted hover:bg-white/10 hover:text-white"
            >
              <CloseIcon className="size-3" />
            </button>
          </span>
        ))}
        {!open && (
          <button
            onClick={() => setOpen(true)}
            className="flex h-8 items-center gap-1 rounded-full border border-dashed border-white/25 px-3 text-xs font-medium text-slate-300 hover:border-white/50 hover:text-white"
          >
            <PlusIcon className="size-3.5" />
            {t.legend.addTag}
          </button>
        )}
      </div>

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

      {open && (
        <div className="rise-in mt-2 rounded-2xl bg-white/[0.05] p-2">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              add(draft);
            }}
            className="flex gap-2"
          >
            <input
              ref={input}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  // Closes this box only, not the field page.
                  e.preventDefault();
                  setOpen(false);
                }
              }}
              placeholder={t.tags.addPlaceholder}
              aria-label={t.tags.add}
              className="h-10 min-w-0 flex-1 rounded-xl bg-black/30 px-3 text-sm outline-none ring-1 ring-white/10 focus:ring-accent/70"
            />
            <button
              type="submit"
              disabled={!draft.trim() || replace.isPending}
              className="h-10 rounded-xl bg-white px-4 text-sm font-medium text-slate-950 disabled:opacity-40"
            >
              {t.tags.add}
            </button>
            <button
              type="button"
              aria-label={t.signIn.close}
              onClick={() => setOpen(false)}
              className="grid size-10 shrink-0 place-items-center rounded-xl text-muted hover:bg-white/10 hover:text-white"
            >
              <CloseIcon className="size-4" />
            </button>
          </form>
          {suggestions.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {suggestions.map((tag) => (
                <button
                  key={tag.id}
                  onClick={() => add(tag.label)}
                  className="flex h-8 items-center gap-1.5 rounded-full px-2.5 text-xs text-slate-300 ring-1 ring-white/10 hover:bg-white/10 hover:text-white"
                >
                  <span
                    className="size-2.5 rounded-full"
                    style={{ background: tag.color }}
                  />
                  {tag.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
