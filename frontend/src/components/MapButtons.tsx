"use client";

import { useState } from "react";

import { BASEMAPS, type Basemap } from "./map/overlay";

const BASEMAP_LABEL: Record<Basemap, string> = { dark: "Dark", light: "Light", satellite: "Satellite" };

type Props = {
  basemap: Basemap;
  onBasemap: (basemap: Basemap) => void;
  onLocate: () => void;
  onAddField: () => void;
  drawing: boolean;
};

function RoundButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`glass grid size-12 place-items-center rounded-full text-lg text-slate-100 disabled:opacity-40 ${props.className ?? ""}`}
    />
  );
}

export function MapButtons({ basemap, onBasemap, onLocate, onAddField, drawing }: Props) {
  const [menu, setMenu] = useState(false);
  return (
    <div className="flex flex-col items-end gap-3">
      <div className="relative">
        <RoundButton aria-label="Map layers" onClick={() => setMenu((m) => !m)} disabled={drawing}>
          ◧
        </RoundButton>
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
                {BASEMAP_LABEL[b]}
              </button>
            ))}
          </div>
        )}
      </div>
      <RoundButton aria-label="Go to my location" onClick={onLocate}>
        ◎
      </RoundButton>
      <RoundButton
        aria-label="Draw a new field"
        onClick={onAddField}
        disabled={drawing}
        className="!bg-accent !text-slate-950 text-2xl font-semibold"
      >
        +
      </RoundButton>
    </div>
  );
}
