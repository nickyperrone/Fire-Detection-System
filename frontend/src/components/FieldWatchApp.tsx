"use client";

import type { Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useMemo, useState } from "react";

import type { Territory } from "@/api/client";
import { usePortfolio, useTerritories } from "@/api/queries";
import { fireTone } from "@/lib/status";
import { formatCamera, useUrlState } from "@/lib/useUrlState";

import { BottomSheet, type Snap } from "./BottomSheet";
import { FieldDetail } from "./FieldDetail";
import { FreshnessPill } from "./FreshnessPill";
import { MapButtons } from "./MapButtons";
import { type MapCamera, MapView, type TerritoryState } from "./map/MapView";
import { useFieldDrawing } from "./map/useFieldDrawing";
import { NewFieldPanel } from "./NewFieldPanel";
import { PortfolioPanel } from "./PortfolioPanel";
import { SearchBar } from "./SearchBar";

function boundsOf(territory: Territory): [[number, number], [number, number]] {
  const points = (territory.geometry.coordinates as number[][][][]).flat(2);
  const lons = points.map((p) => p[0]);
  const lats = points.map((p) => p[1]);
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ];
}

export function FieldWatchApp() {
  const url = useUrlState();
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const [snap, setSnap] = useState<Snap>("peek");
  const [drawingActive, setDrawingActive] = useState(false);
  const [tilesVersion, setTilesVersion] = useState(0);

  const everything = usePortfolio([]);
  const filtered = usePortfolio(url.tags);
  const territories = useTerritories();
  // Opening the sheet when the shape closes leaves room for the name and tags form.
  const drawing = useFieldDrawing(map, drawingActive, () => setSnap("half"));

  const territoryById = useMemo(
    () => new Map((territories.data ?? []).map((t) => [t.id, t])),
    [territories.data],
  );
  const allTags = useMemo(
    () => [...new Set((territories.data ?? []).flatMap((t) => t.tags))].sort(),
    [territories.data],
  );
  const territoryStates = useMemo(() => {
    const shown = new Set((filtered.data ?? []).map((e) => e.territory_id));
    return new Map<number, TerritoryState>(
      (everything.data ?? []).map((e) => [
        e.territory_id,
        { tone: fireTone(e.fire), dimmed: url.tags.length > 0 && !shown.has(e.territory_id) },
      ]),
    );
  }, [everything.data, filtered.data, url.tags]);
  const selected = everything.data?.find((e) => e.territory_id === url.selectedId) ?? null;

  const flyTo = useCallback(
    (territory: Territory) => {
      const mobile = window.innerWidth < 768;
      map?.fitBounds(boundsOf(territory), {
        padding: mobile
          ? { top: 90, bottom: window.innerHeight * 0.5, left: 30, right: 30 }
          : { top: 60, bottom: 60, left: 440, right: 60 },
        maxZoom: 15,
        duration: 900,
      });
    },
    [map],
  );

  const select = useCallback(
    (id: number | null) => {
      url.update({ f: id === null ? null : String(id) });
      setSnap(id === null ? "peek" : "half");
      const territory = id === null ? undefined : territoryById.get(id);
      if (territory) flyTo(territory);
    },
    [url, territoryById, flyTo],
  );

  const onCameraChange = useCallback(
    (camera: MapCamera) => url.update({ v: formatCamera(camera) }),
    [url],
  );

  const toggleTag = (tag: string) =>
    url.update({ tag: url.tags.includes(tag) ? url.tags.filter((t) => t !== tag) : [...url.tags, tag] });

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

  return (
    <main className="fixed inset-0">
      <MapView
        basemap={url.basemap}
        initialCamera={url.initialCamera}
        territoryStates={territoryStates}
        territoriesVersion={tilesVersion}
        selectedId={url.selectedId}
        interactive={!drawingActive}
        onSelect={select}
        onCameraChange={onCameraChange}
        onReady={setMap}
      />

      <div className="pointer-events-none absolute inset-x-3 top-3 z-10 flex flex-col gap-2 pt-[env(safe-area-inset-top)] md:left-[424px] md:right-auto md:w-[380px]">
        <div className="pointer-events-auto">
          <SearchBar territories={territories.data ?? []} onPick={(t) => select(t.id)} />
        </div>
        <div className="pointer-events-auto">
          <FreshnessPill />
        </div>
      </div>

      <div className="absolute right-3 top-[120px] z-10 md:top-3">
        <MapButtons
          basemap={url.basemap}
          onBasemap={(b) => url.update({ b })}
          onLocate={locate}
          onAddField={() => {
            setDrawingActive(true);
            setSnap("peek");
          }}
          drawing={drawingActive}
        />
      </div>

      <BottomSheet
        snap={snap}
        onSnapChange={setSnap}
        contentKey={drawingActive ? "draw" : String(url.selectedId ?? "portfolio")}
      >
        {drawingActive ? (
          <NewFieldPanel
            drawing={drawing}
            fields={(territories.data ?? []).filter((t) => t.kind === "FIELD")}
            defaultParentId={selected?.kind === "FIELD" ? selected.territory_id : null}
            onDone={finishDrawing}
          />
        ) : everything.isError ? (
          <p className="text-sm text-critical">Cannot reach the Field Watch API.</p>
        ) : selected ? (
          <FieldDetail
            entry={selected}
            parentName={selected.parent_id ? (territoryById.get(selected.parent_id)?.name ?? null) : null}
            onClose={() => select(null)}
          />
        ) : hasFields || url.tags.length ? (
          <PortfolioPanel
            entries={filtered.data ?? []}
            allTags={allTags}
            activeTags={url.tags}
            onToggleTag={toggleTag}
            onSelect={select}
          />
        ) : (
          everything.data && (
            <div className="space-y-2">
              <h2 className="text-lg font-semibold">Fires in Entre Ríos and the Delta</h2>
              <p className="text-sm text-slate-300">
                The map shows satellite fire detections as they arrive. Draw your first field with + to
                see its distance to fires and when it is good to spray.
              </p>
            </div>
          )
        )}
      </BottomSheet>
    </main>
  );
}
