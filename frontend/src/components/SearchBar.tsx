"use client";

import { useMemo, useState } from "react";

import type { Place, Territory } from "@/api/client";
import { usePlaces } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import { formatHectares } from "@/i18n/text";
import { useSettled } from "@/lib/useSettled";

import { SearchIcon } from "./Icons";

type Props = {
  territories: Territory[];
  onPick: (territory: Territory) => void;
  onPickPlace: (place: Place) => void;
};

// Places are asked for once typing pauses this long, not on every letter.
const PLACE_DELAY_MS = 300;

/** The user's fields, lots and tags first, then places in Argentina (docs/04-frontend.md). */
export function SearchBar({ territories, onPick, onPickPlace }: Props) {
  const { t } = useLocale();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const settled = useSettled(query, PLACE_DELAY_MS);
  const places = usePlaces(settled);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return territories
      .filter(
        (x) =>
          x.name.toLowerCase().includes(q) ||
          x.tags.some((tag) => tag.toLowerCase().includes(q)),
      )
      .slice(0, 6);
  }, [query, territories]);
  const found = query.trim() ? (places.data ?? []) : [];
  const done = () => {
    setQuery("");
    setOpen(false);
  };

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
      {open &&
        (matches.length > 0 || found.length > 0 || places.isFetching) && (
          <div className="glass absolute inset-x-0 top-14 max-h-[60dvh] overflow-y-auto rounded-2xl py-1">
            {matches.length > 0 && (
              <Group title={t.search.yours}>
                {matches.map((territory) => (
                  <Row
                    key={territory.id}
                    onPick={() => {
                      onPick(territory);
                      done();
                    }}
                    name={territory.name}
                    detail={`${territory.kind === "SECTION" ? `${t.search.lot} · ` : ""}${formatHectares(t, territory.hectares)}`}
                  />
                ))}
              </Group>
            )}
            {(found.length > 0 || places.isFetching) && (
              <Group title={t.search.places}>
                {found.length === 0 ? (
                  <li className="px-4 py-3 text-sm text-muted">
                    {t.search.searching}
                  </li>
                ) : (
                  found.map((place) => (
                    <Row
                      key={`${place.longitude},${place.latitude},${place.name}`}
                      onPick={() => {
                        onPickPlace(place);
                        done();
                      }}
                      name={place.name}
                      detail={place.context}
                    />
                  ))
                )}
              </Group>
            )}
          </div>
        )}
    </div>
  );
}

function Group({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h3 className="px-4 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-muted">
        {title}
      </h3>
      <ul>{children}</ul>
    </section>
  );
}

function Row({
  name,
  detail,
  onPick,
}: {
  name: string;
  detail: string;
  onPick: () => void;
}) {
  return (
    <li>
      <button
        onMouseDown={(e) => e.preventDefault()}
        onClick={onPick}
        className="block w-full px-4 py-2.5 text-left hover:bg-white/5"
      >
        <span className="block truncate text-sm">{name}</span>
        <span className="block truncate text-xs text-muted">{detail}</span>
      </button>
    </li>
  );
}
