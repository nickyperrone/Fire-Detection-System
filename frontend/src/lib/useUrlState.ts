"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import { BASEMAPS, type Basemap } from "@/components/map/overlay";
import type { MapCamera } from "@/components/map/MapView";

// The whole country: a first visit starts here and then flies to Larroque (FieldWatchApp).
const DEFAULT_CAMERA: MapCamera = { lat: -38.5, lon: -64.5, zoom: 3.4 };

type Changes = Partial<{
  f: string | null;
  tag: string[];
  b: string;
  v: string;
  s: string[];
  only: string | null;
  r: string | null;
  p: string | null;
  c: string | null;
  signin: string | null;
  tab: string | null;
}>;

function parseCamera(value: string | null): MapCamera {
  const [lat, lon, zoom] = (value ?? "").split(",").map(Number);
  return [lat, lon, zoom].every(Number.isFinite) && value
    ? { lat, lon, zoom }
    : DEFAULT_CAMERA;
}

export function formatCamera({ lat, lon, zoom }: MapCamera): string {
  return `${lat.toFixed(5)},${lon.toFixed(5)},${zoom.toFixed(2)}`;
}

/** The sections of a field's page (docs/12-field-page.md#tabs). */
export const FIELD_TABS = ["now", "photos", "history", "settings"] as const;
export type FieldTab = (typeof FIELD_TABS)[number];

/** What colors the fields on the map (docs/01-product.md#tags-and-colors). */
export type ColorBy = "status" | "tags";

/**
 * App state that belongs in a shareable link: the open field (f) and its tab (tab), tag filters
 * (tag), the fields picked to compare (s) and whether only those are shown (only), basemap (b),
 * field colors (c) and camera (v).
 */
export function useUrlState() {
  const params = useSearchParams();

  const selectedId = params.get("f") ? Number(params.get("f")) : null;
  const tabParam = params.get("tab") as FieldTab | null;
  const tab: FieldTab =
    tabParam && FIELD_TABS.includes(tabParam) ? tabParam : "now";
  const tagsKey = params.getAll("tag").join("\n");
  const tags = useMemo(() => (tagsKey ? tagsKey.split("\n") : []), [tagsKey]);
  const pickedKey = params.getAll("s").join(",");
  const picked = useMemo(
    () =>
      pickedKey
        ? pickedKey.split(",").map(Number).filter(Number.isInteger)
        : [],
    [pickedKey],
  );
  const onlyPicked = params.get("only") === "1" && picked.length > 0;
  const showRisk = params.get("r") === "1";
  // Set by the API when an email link was used or expired (docs/09-accounts-and-alerts.md).
  const signinExpired = params.get("signin") === "expired";
  const colorBy: ColorBy = params.get("c") === "tags" ? "tags" : "status";
  // Property lines are on unless the link turns them off.
  const showParcels = params.get("p") !== "0";
  const basemapParam = params.get("b") as Basemap | null;
  const basemap =
    basemapParam && BASEMAPS.includes(basemapParam) ? basemapParam : "dark";
  // Read once: afterwards the map owns the camera and only writes it back.
  const initialCamera = useMemo(() => parseCamera(params.get("v")), []); // eslint-disable-line react-hooks/exhaustive-deps
  const linkHasCamera = useMemo(() => params.has("v"), []); // eslint-disable-line react-hooks/exhaustive-deps

  // `push`: a step the browser's back button should undo, like opening a field or a tab.
  const update = useCallback((changes: Changes, push = false) => {
    const next = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries(changes)) {
      next.delete(key);
      if (Array.isArray(value)) value.forEach((v) => next.append(key, v));
      else if (value !== null && value !== undefined) next.set(key, value);
    }
    // Next.js syncs useSearchParams with the native History API, without a navigation.
    if (push) window.history.pushState(null, "", `?${next}`);
    else window.history.replaceState(null, "", `?${next}`);
  }, []);

  return {
    selectedId,
    tab,
    tags,
    picked,
    onlyPicked,
    showRisk,
    showParcels,
    colorBy,
    signinExpired,
    basemap,
    initialCamera,
    linkHasCamera,
    update,
  };
}
