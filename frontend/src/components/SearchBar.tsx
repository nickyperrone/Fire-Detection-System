"use client";

import { useMemo, useState } from "react";

import type { Territory } from "@/api/client";
import { formatHectares } from "@/lib/format";

type Props = { territories: Territory[]; onPick: (territory: Territory) => void };

export function SearchBar({ territories, onPick }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return territories
      .filter((t) => t.name.toLowerCase().includes(q) || t.tags.some((tag) => tag.toLowerCase().includes(q)))
      .slice(0, 6);
  }, [query, territories]);

  return (
    <div className="relative">
      <input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Search fields, lots or tags"
        aria-label="Search fields"
        className="glass h-12 w-full rounded-2xl px-4 text-[15px] text-slate-100 outline-none placeholder:text-muted focus:ring-2 focus:ring-accent/60"
      />
      {open && matches.length > 0 && (
        <ul className="glass absolute inset-x-0 top-14 overflow-hidden rounded-2xl">
          {matches.map((t) => (
            <li key={t.id}>
              <button
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onPick(t);
                  setQuery("");
                  setOpen(false);
                }}
                className="flex w-full items-center justify-between px-4 py-3 text-left text-sm hover:bg-white/5"
              >
                <span>{t.name}</span>
                <span className="text-xs text-muted">
                  {t.kind === "SECTION" ? "lot · " : ""}
                  {formatHectares(t.hectares)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
