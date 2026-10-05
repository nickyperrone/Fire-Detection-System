"use client";

import type { Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { PortfolioEntry, Territory } from "@/api/client";
import {
  useBoundary,
  useAnomalyPatches,
  useMe,
  usePortfolio,
  useTags,
  useTerritories,
} from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import { hazardTone, TONE_HEX } from "@/lib/status";
import { leadingTag } from "@/lib/tags";
import { formatCamera, useUrlState } from "@/lib/useUrlState";

import { BottomSheet, type Snap } from "./BottomSheet";
import { DrawFieldOverlay } from "./DrawFieldOverlay";
import { FieldDetail } from "./FieldDetail";
import { FreshnessPill } from "./FreshnessPill";
import { AccountButton } from "./AccountButton";
import { LanguageSwitch } from "./LanguageSwitch";
import { MapButtons } from "./MapButtons";
import { type MapCamera, MapView, type TerritoryState } from "./map/MapView";
import { useFieldDrawing } from "./map/useFieldDrawing";
import { useDangerAlerts } from "./useDangerAlerts";
import { PortfolioPanel } from "./PortfolioPanel";
import { SearchBar } from "./SearchBar";
import { SignInCard } from "./SignInCard";

type Bounds = [[number, number], [number, number]];

const LARROQUE: [number, number] = [-59.01, -33.04];
const OPENING_FLIGHT_MS = 3000;
const OPENING_PAUSE_MS = 700;

function boundsOf(territories: Territory[]): Bounds | null {
  const points = territories.flatMap((t) =>
    (t.geometry.coordinates as number[][][][]).flat(2),
  );
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
    if (e.parent_id !== null && picked.has(e.parent_id))
      picked.add(e.territory_id);
  }
  return picked;
}

export function FieldWatchApp() {
  const { t } = useLocale();
  const url = useUrlState();
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const [snap, setSnap] = useState<Snap>("peek");
  const [drawingActive, setDrawingActive] = useState(false);
  // The field whose outline is being edited; drawing then makes a piece to add or remove.
  const [editingId, setEditingId] = useState<number | null>(null);
  const [tilesVersion, setTilesVersion] = useState(0);

  const me = useMe();
  const signedIn = Boolean(me.data);
  // "expired" when the email link the user came back with no longer works.
  const [signIn, setSignIn] = useState<"open" | "expired" | null>(() =>
    url.signinExpired ? "expired" : null,
  );
  const everything = usePortfolio([], signedIn);
  const filtered = usePortfolio(url.tags, signedIn);
  const territories = useTerritories(signedIn);
  const tags = useTags(signedIn);
  const boundary = useBoundary();

  const territoryById = useMemo(
    () => new Map((territories.data ?? []).map((t) => [t.id, t])),
    [territories.data],
  );
  const editing = editingId !== null ? territoryById.get(editingId) : undefined;
  const drawingOn = drawingActive || editing !== undefined;
  const drawing = useFieldDrawing(map, drawingOn);
  // A hidden field hides its lots too.
  const hiddenIds = useMemo(() => {
    const entries = everything.data ?? [];
    const off = new Set(
      entries.filter((e) => !e.visible).map((e) => e.territory_id),
    );
    return new Set(
      entries
        .filter(
          (e) =>
            off.has(e.territory_id) ||
            (e.parent_id !== null && off.has(e.parent_id)),
        )
        .map((e) => e.territory_id),
    );
  }, [everything.data]);
  useDangerAlerts(everything.data, t);
  // In the API's order (plain labels first), the order that decides a field's color.
  const allTags = useMemo(() => {
    const used = new Set((territories.data ?? []).flatMap((t) => t.tags));
    return (tags.data?.tags ?? [])
      .map((tag) => tag.label)
      .filter((label) => used.has(label));
  }, [territories.data, tags.data]);
  const pickedWithLots = useMemo(
    () => withLots(url.picked, everything.data ?? []),
    [url.picked, everything.data],
  );
  const listed = useMemo(() => {
    const entries = filtered.data ?? [];
    return url.onlyPicked
      ? entries.filter((e) => pickedWithLots.has(e.territory_id))
      : entries;
  }, [filtered.data, url.onlyPicked, pickedWithLots]);
  const tagColors = useMemo(
    () => new Map((tags.data?.tags ?? []).map((tag) => [tag.label, tag.color])),
    [tags.data],
  );
  const territoryStates = useMemo(() => {
    const shown = new Set(listed.map((e) => e.territory_id));
    const narrowed = url.tags.length > 0 || url.onlyPicked;
    const entries = everything.data ?? [];
    const byId = new Map(entries.map((e) => [e.territory_id, e]));
    // With tags, a lot takes its field's color; only a lot of an untagged field uses its own.
    const ownColor = (e: PortfolioEntry): string | undefined => {
      const tag = leadingTag(e.tags);
      return tag ? tagColors.get(tag) : undefined;
    };
    const tagColor = (e: PortfolioEntry): string | undefined => {
      const parent = e.parent_id !== null ? byId.get(e.parent_id) : undefined;
      return (parent && ownColor(parent)) ?? ownColor(e);
    };
    return new Map<number, TerritoryState>(
      entries.map((e) => [
        e.territory_id,
        {
          color:
            url.colorBy === "tags"
              ? (tagColor(e) ?? TONE_HEX.unknown)
              : TONE_HEX[hazardTone(e.fire, e.lightning)],
          dimmed: narrowed && !shown.has(e.territory_id),
          picked: url.picked.includes(e.territory_id),
        },
      ]),
    );
  }, [
    everything.data,
    listed,
    url.tags,
    url.onlyPicked,
    url.picked,
    url.colorBy,
    tagColors,
  ]);
  const selected =
    everything.data?.find((e) => e.territory_id === url.selectedId) ?? null;
  const patches = useAnomalyPatches(selected?.territory_id ?? null);

  const frame = useCallback(
    (targets: Territory[], duration = 900) => {
      const bounds = boundsOf(targets);
      if (!bounds) return;
      const mobile = window.innerWidth < 768;
      map?.fitBounds(bounds, {
        padding: mobile
          ? { top: 140, bottom: window.innerHeight * 0.5, left: 30, right: 70 }
          : { top: 60, bottom: 60, left: 440, right: 60 },
        maxZoom: 15,
        duration,
      });
    },
    [map],
  );

  // First visit without a camera in the link: start over Argentina and fly to the fields
  // around Larroque (or to Larroque itself before there are any). MapLibre skips the animation
  // for people who ask their system for reduced motion.
  const flewIn = useRef(false);
  useEffect(() => {
    if (flewIn.current || url.linkHasCamera || !map || !territories.data)
      return;
    flewIn.current = true;
    const fields = territories.data.filter((t) => t.kind === "FIELD");
    const flyIn = () => {
      if (fields.length) frame(fields, OPENING_FLIGHT_MS);
      else
        map.flyTo({ center: LARROQUE, zoom: 11, duration: OPENING_FLIGHT_MS });
    };
    // A short look at the whole country first. "load" has usually fired by the time the fields
    // arrive, and a missed event would leave the map over Argentina.
    if (map.loaded()) window.setTimeout(flyIn, OPENING_PAUSE_MS);
    else map.once("load", () => window.setTimeout(flyIn, OPENING_PAUSE_MS));
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
      url.update({
        s: next.map(String),
        only: next.length && url.onlyPicked ? "1" : null,
      });
    },
    [url],
  );

  const showOnlyPicked = () => {
    url.update({ only: "1", f: null });
    frame(
      url.picked
        .map((id) => territoryById.get(id))
        .filter((t): t is Territory => !!t),
    );
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
      tag: url.tags.includes(tag)
        ? url.tags.filter((t) => t !== tag)
        : [...url.tags, tag],
    });

  const locate = () =>
    navigator.geolocation?.getCurrentPosition((position) =>
      map?.flyTo({
        center: [position.coords.longitude, position.coords.latitude],
        zoom: 13,
      }),
    );

  const finishDrawing = (created: Territory | null) => {
    setDrawingActive(false);
    setEditingId(null);
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
        hiddenIds={hiddenIds}
        // Field tiles depend on the session cookie: fetch them again on signing in or out.
        territoriesVersion={tilesVersion * 2 + Number(signedIn)}
        selectedId={url.selectedId}
        interactive={!drawingOn}
        onSelect={onMapSelect}
        onCameraChange={onCameraChange}
        onReady={setMap}
        messages={t}
        showRisk={url.showRisk}
        showParcels={url.showParcels || drawingOn}
        boundary={boundary.data ?? null}
        grayOutside={drawingOn}
        patches={selected && !drawingOn ? (patches.data ?? null) : null}
      />

      {drawingOn ? (
        <DrawFieldOverlay
          drawing={drawing}
          editing={editing ?? null}
          fields={fields}
          defaultParentId={
            selected?.kind === "FIELD" ? selected.territory_id : null
          }
          onDone={finishDrawing}
        />
      ) : (
        <>
          <div className="pointer-events-none absolute inset-x-3 top-3 z-10 flex flex-col gap-2 pt-[env(safe-area-inset-top)] md:left-[424px] md:right-auto md:w-[380px]">
            <div className="pointer-events-auto">
              <SearchBar
                territories={territories.data ?? []}
                onPick={(t) => open(t.id)}
              />
            </div>
            <div className="pointer-events-auto flex items-center justify-between gap-2">
              <div className="min-w-0">
                <FreshnessPill />
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <LanguageSwitch />
                {me.isSuccess && (
                  <AccountButton
                    me={me.data}
                    onSignIn={() => setSignIn("open")}
                  />
                )}
              </div>
            </div>
          </div>

          <div className="absolute right-3 top-[120px] z-10 md:top-3">
            <MapButtons
              basemap={url.basemap}
              onBasemap={(b) => url.update({ b })}
              showRisk={url.showRisk}
              onToggleRisk={() => url.update({ r: url.showRisk ? null : "1" })}
              showParcels={url.showParcels}
              onToggleParcels={() =>
                url.update({ p: url.showParcels ? "0" : null })
              }
              colorBy={url.colorBy}
              onColorBy={(c) => url.update({ c: c === "tags" ? c : null })}
              onGoToFields={() =>
                signedIn ? frame(fields) : setSignIn("open")
              }
              onLocate={locate}
              onAddField={() =>
                signedIn ? setDrawingActive(true) : setSignIn("open")
              }
            />
          </div>

          <BottomSheet
            snap={snap}
            onSnapChange={setSnap}
            contentKey={String(url.selectedId ?? "portfolio")}
          >
            {me.isSuccess && !signedIn ? (
              <div className="space-y-3">
                <h2 className="text-lg font-semibold">{t.app.exploreTitle}</h2>
                <p className="text-sm text-slate-300">
                  {t.signIn.signedOutBody}
                </p>
                <button
                  onClick={() => setSignIn("open")}
                  className="h-11 rounded-xl bg-accent px-5 font-semibold text-slate-950"
                >
                  {t.signIn.button}
                </button>
              </div>
            ) : everything.isError ? (
              <p className="text-sm text-bad">{t.app.apiDown}</p>
            ) : selected ? (
              <FieldDetail
                entry={selected}
                parentName={
                  selected.parent_id
                    ? (territoryById.get(selected.parent_id)?.name ?? null)
                    : null
                }
                onClose={() => open(null)}
                onEditOutline={() => setEditingId(selected.territory_id)}
              />
            ) : hasFields || url.tags.length ? (
              <PortfolioPanel
                entries={listed}
                hidden={hiddenIds}
                tagColors={tagColors}
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
                  <h2 className="text-lg font-semibold">
                    {t.app.exploreTitle}
                  </h2>
                  <p className="text-sm text-slate-300">{t.app.exploreBody}</p>
                </div>
              )
            )}
          </BottomSheet>
          {signIn && (
            <SignInCard
              expired={signIn === "expired"}
              onClose={() => {
                setSignIn(null);
                url.update({ signin: null });
              }}
            />
          )}
        </>
      )}
    </main>
  );
}
