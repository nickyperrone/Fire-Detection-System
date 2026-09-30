"use client";

import type { Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { PortfolioEntry, Territory } from "@/api/client";
import { usePortfolio, useTerritories } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import { hazardTone } from "@/lib/status";
import { formatCamera, useUrlState } from "@/lib/useUrlState";

import { BottomSheet, type Snap } from "./BottomSheet";
import { DrawFieldOverlay } from "./DrawFieldOverlay";
import { FieldDetail } from "./FieldDetail";
import { FreshnessPill } from "./FreshnessPill";
import { LanguageSwitch } from "./LanguageSwitch";
import { MapButtons } from "./MapButtons";
import { type MapCamera, MapView, type TerritoryState } from "./map/MapView";
import { useFieldDrawing } from "./map/useFieldDrawing";
import { PortfolioPanel } from "./PortfolioPanel";
import { SearchBar } from "./SearchBar";

type Bounds = [[number, number], [number, number]];

function boundsOf(territories: Territory[]): Bounds | null {
  const points = territories.flatMap((t) => (t.geometry.coordinates as number[][][][]).flat(2));
  if (points.length === 0) return null;
  const lons = points.map((p) => p[0]);
  const lats = points.map((p) => p[1]);
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ];
}

/** Picked fields plus their lots: picking a field brings its lots along. */
function withLots(ids: number[], entries: PortfolioEntry[]): Set<number> {
  const picked = new Set(ids);
  for (const e of entries) {
    if (e.parent_id !== null && picked.has(e.parent_id)) picked.add(e.territory_id);
  }
  return picked;
}

export function FieldWatchApp() {
  const { t } = useLocale();
  const url = useUrlState();
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const [snap, setSnap] = useState<Snap>("peek");
  const [drawingActive, setDrawingActive] = useState(false);
  const [tilesVersion, setTilesVersion] = useState(0);

  const everything = usePortfolio([]);
  const filtered = usePortfolio(url.tags);
  const territories = useTerritories();
  const drawing = useFieldDrawing(map, drawingActive);

  const territoryById = useMemo(
    () => new Map((territories.data ?? []).map((t) => [t.id, t])),
    [territories.data],
  );
  const allTags = useMemo(
    () => [...new Set((territories.data ?? []).flatMap((t) => t.tags))].sort(),
    [territories.data],
  );
  const pickedWithLots = useMemo(
    () => withLots(url.picked, everything.data ?? []),
    [url.picked, everything.data],
  );
  const listed = useMemo(() => {
    const entries = filtered.data ?? [];
    return url.onlyPicked ? entries.filter((e) => pickedWithLots.has(e.territory_id)) : entries;
  }, [filtered.data, url.onlyPicked, pickedWithLots]);
  const territoryStates = useMemo(() => {
    const shown = new Set(listed.map((e) => e.territory_id));
    const narrowed = url.tags.length > 0 || url.onlyPicked;
    return new Map<number, TerritoryState>(
      (everything.data ?? []).map((e) => [
        e.territory_id,
        {
          tone: hazardTone(e.fire, e.lightning),
          dimmed: narrowed && !shown.has(e.territory_id),
          picked: url.picked.includes(e.territory_id),
        },
      ]),
    );
  }, [everything.data, listed, url.tags, url.onlyPicked, url.picked]);
  const selected = everything.data?.find((e) => e.territory_id === url.selectedId) ?? null;

  const frame = useCallback(
    (targets: Territory[]) => {
      const bounds = boundsOf(targets);
      if (!bounds) return;
      const mobile = window.innerWidth < 768;
      map?.fitBounds(bounds, {
        padding: mobile
          ? { top: 140, bottom: window.innerHeight * 0.5, left: 30, right: 70 }
          : { top: 60, bottom: 60, left: 440, right: 60 },
        maxZoom: 15,
        duration: 900,
      });
    },
    [map],
  );

  // First visit without a camera in the link: frame every field instead of a fixed point.
  const framedOnce = useRef(false);
  useEffect(() => {
    const all = territories.data ?? [];
    if (framedOnce.current || url.linkHasCamera || !map || all.length === 0) return;
    framedOnce.current = true;
    frame(all.filter((t) => t.kind === "FIELD"));
  }, [map, territories.data, url.linkHasCamera, frame]);

  const open = useCallback(
    (id: number | null) => {
      url.update({ f: id === null ? null : String(id) });
      setSnap(id === null ? "peek" : "half");
      const territory = id === null ? undefined : territoryById.get(id);
      if (territory) frame([territory]);
    },
    [url, territoryById, frame],
  );

  const togglePick = useCallback(
    (id: number) => {
      const next = url.picked.includes(id)
        ? url.picked.filter((p) => p !== id)
        : [...url.picked, id];
      url.update({ s: next.map(String), only: next.length && url.onlyPicked ? "1" : null });
    },
    [url],
  );

  const showOnlyPicked = () => {
    url.update({ only: "1", f: null });
    frame(url.picked.map((id) => territoryById.get(id)).filter((t): t is Territory => !!t));
    setSnap("half");
  };

  // Shift or Cmd click on the map adds a field to the selection, as in most map apps.
  const onMapSelect = useCallback(
    (id: number | null, additive: boolean) => {
      if (additive && id !== null) togglePick(id);
      else open(id);
    },
    [togglePick, open],
  );

  const onCameraChange = useCallback(
    (camera: MapCamera) => url.update({ v: formatCamera(camera) }),
    [url],
  );

  const toggleTag = (tag: string) =>
    url.update({
      tag: url.tags.includes(tag) ? url.tags.filter((t) => t !== tag) : [...url.tags, tag],
    });

  const locate = () =>
    navigator.geolocation?.getCurrentPosition((position) =>
      map?.flyTo({ center: [position.coords.longitude, position.coords.latitude], zoom: 13 }),
    );

  const finishDrawing = (created: Territory | null) => {
    setDrawingActive(false);
    if (!created) return;
    setTilesVersion((v) => v + 1);
    url.update({ f: String(created.id) });
    setSnap("half");
  };

  const hasFields = (everything.data?.length ?? 0) > 0;
  const fields = (territories.data ?? []).filter((t) => t.kind === "FIELD");

  return (
    <main className="fixed inset-0">
      <MapView
        basemap={url.basemap}
        initialCamera={url.initialCamera}
        territoryStates={territoryStates}
        territoriesVersion={tilesVersion}
        selectedId={url.selectedId}
        interactive={!drawingActive}
        onSelect={onMapSelect}
        onCameraChange={onCameraChange}
        onReady={setMap}
        messages={t}
      />

      {drawingActive ? (
        <DrawFieldOverlay
          drawing={drawing}
          fields={fields}
          defaultParentId={selected?.kind === "FIELD" ? selected.territory_id : null}
          onDone={finishDrawing}
        />
      ) : (
        <>
          <div className="pointer-events-none absolute inset-x-3 top-3 z-10 flex flex-col gap-2 pt-[env(safe-area-inset-top)] md:left-[424px] md:right-auto md:w-[380px]">
            <div className="pointer-events-auto">
              <SearchBar territories={territories.data ?? []} onPick={(t) => open(t.id)} />
            </div>
            <div className="pointer-events-auto flex items-center justify-between gap-2">
              <FreshnessPill />
              <LanguageSwitch />
            </div>
          </div>

          <div className="absolute right-3 top-[120px] z-10 md:top-3">
            <MapButtons
              basemap={url.basemap}
              onBasemap={(b) => url.update({ b })}
              onLocate={locate}
              onAddField={() => setDrawingActive(true)}
            />
          </div>

          <BottomSheet
            snap={snap}
            onSnapChange={setSnap}
            contentKey={String(url.selectedId ?? "portfolio")}
          >
            {everything.isError ? (
              <p className="text-sm text-bad">{t.app.apiDown}</p>
            ) : selected ? (
              <FieldDetail
                entry={selected}
                parentName={
                  selected.parent_id ? (territoryById.get(selected.parent_id)?.name ?? null) : null
                }
                onClose={() => open(null)}
              />
            ) : hasFields || url.tags.length ? (
              <PortfolioPanel
                entries={listed}
                allTags={allTags}
                activeTags={url.tags}
                picked={url.picked}
                onlyPicked={url.onlyPicked}
                onToggleTag={toggleTag}
                onTogglePick={togglePick}
                onShowOnlyPicked={showOnlyPicked}
                onShowAll={() => url.update({ only: null })}
                onClearPicked={() => url.update({ s: [], only: null })}
                onSelect={open}
              />
            ) : (
              everything.data && (
                <div className="space-y-2">
                  <h2 className="text-lg font-semibold">{t.app.exploreTitle}</h2>
                  <p className="text-sm text-slate-300">{t.app.exploreBody}</p>
                </div>
              )
            )}
          </BottomSheet>
        </>
      )}
    </main>
  );
}
