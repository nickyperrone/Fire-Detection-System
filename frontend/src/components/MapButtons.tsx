"use client";

import { useState } from "react";

import { useLocale } from "@/i18n/LocaleProvider";

import { LayersIcon, LocateIcon, PlusIcon } from "./Icons";
import { BASEMAPS, type Basemap } from "./map/overlay";

type Props = {
  basemap: Basemap;
  onBasemap: (basemap: Basemap) => void;
  onLocate: () => void;
  onAddField: () => void;
};

const ROUND = "glass grid size-12 place-items-center rounded-full text-slate-100";

export function MapButtons({ basemap, onBasemap, onLocate, onAddField }: Props) {
  const { t } = useLocale();
  const [menu, setMenu] = useState(false);
  return (
    <div className="flex flex-col items-end gap-3">
      <div className="relative">
        <button aria-label={t.buttons.layers} aria-expanded={menu} onClick={() => setMenu((m) => !m)} className={ROUND}>
          <LayersIcon />
        </button>
        {menu && (
          <div className="glass absolute right-14 top-0 flex overflow-hidden rounded-2xl">
            {BASEMAPS.map((b) => (
              <button
                key={b}
                onClick={() => {
                  onBasemap(b);
                  setMenu(false);
                }}
                className={`px-3 py-3 text-sm ${b === basemap ? "text-accent" : "text-slate-200"}`}
              >
                {t.basemaps[b]}
              </button>
            ))}
          </div>
        )}
      </div>
      <button aria-label={t.buttons.locate} onClick={onLocate} className={ROUND}>
        <LocateIcon />
      </button>
      <button
        aria-label={t.buttons.addFieldLabel}
        title={t.buttons.addFieldLabel}
        onClick={onAddField}
        className="group flex h-12 items-center rounded-full bg-accent px-3.5 font-semibold text-slate-950 shadow-lg shadow-black/40"
      >
        <PlusIcon />
        {/* The label slides out on hover or focus; on touch screens the icon is enough. */}
        <span className="max-w-0 overflow-hidden whitespace-nowrap transition-all duration-200 group-hover:ml-1.5 group-hover:max-w-40 group-focus-visible:ml-1.5 group-focus-visible:max-w-40">
          {t.buttons.addField}
        </span>
      </button>
    </div>
  );
}
