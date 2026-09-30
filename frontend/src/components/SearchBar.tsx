"use client";

import { useMemo, useState } from "react";

import type { Territory } from "@/api/client";
import { useLocale } from "@/i18n/LocaleProvider";
import { formatHectares } from "@/i18n/text";

import { SearchIcon } from "./Icons";

type Props = { territories: Territory[]; onPick: (territory: Territory) => void };

export function SearchBar({ territories, onPick }: Props) {
  const { t } = useLocale();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return territories
      .filter((x) => x.name.toLowerCase().includes(q) || x.tags.some((tag) => tag.toLowerCase().includes(q)))
      .slice(0, 6);
  }, [query, territories]);

  return (
    <div className="relative">
      <SearchIcon className="pointer-events-none absolute left-4 top-1/2 z-10 size-5 -translate-y-1/2 text-muted" />
      <input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={t.search.placeholder}
        aria-label={t.search.placeholder}
        className="glass h-12 w-full rounded-2xl pl-12 pr-4 text-[15px] text-slate-100 outline-none placeholder:text-muted focus:ring-2 focus:ring-accent/60"
      />
      {open && matches.length > 0 && (
        <ul className="glass absolute inset-x-0 top-14 overflow-hidden rounded-2xl">
          {matches.map((territory) => (
            <li key={territory.id}>
              <button
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onPick(territory);
                  setQuery("");
                  setOpen(false);
                }}
                className="flex w-full items-center justify-between px-4 py-3 text-left text-sm hover:bg-white/5"
              >
                <span>{territory.name}</span>
                <span className="text-xs text-muted">
                  {territory.kind === "SECTION" ? `${t.search.lot} · ` : ""}
                  {formatHectares(t, territory.hectares)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
