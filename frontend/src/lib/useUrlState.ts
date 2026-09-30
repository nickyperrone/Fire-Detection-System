"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import { BASEMAPS, type Basemap } from "@/components/map/overlay";
import type { MapCamera } from "@/components/map/MapView";

// Larroque, Entre Ríos: where the first fields are.
const DEFAULT_CAMERA: MapCamera = { lat: -32.97, lon: -59.05, zoom: 10.5 };

type Changes = Partial<{ f: string | null; tag: string[]; b: string; v: string }>;

function parseCamera(value: string | null): MapCamera {
  const [lat, lon, zoom] = (value ?? "").split(",").map(Number);
  return [lat, lon, zoom].every(Number.isFinite) && value ? { lat, lon, zoom } : DEFAULT_CAMERA;
}

export function formatCamera({ lat, lon, zoom }: MapCamera): string {
  return `${lat.toFixed(5)},${lon.toFixed(5)},${zoom.toFixed(2)}`;
}

/** App state that belongs in a shareable link: selected field, tag filters, basemap, camera. */
export function useUrlState() {
  const params = useSearchParams();

  const selectedId = params.get("f") ? Number(params.get("f")) : null;
  const tagsKey = params.getAll("tag").join("\n");
  const tags = useMemo(() => (tagsKey ? tagsKey.split("\n") : []), [tagsKey]);
  const basemapParam = params.get("b") as Basemap | null;
  const basemap = basemapParam && BASEMAPS.includes(basemapParam) ? basemapParam : "dark";
  // Read once: afterwards the map owns the camera and only writes it back.
  const initialCamera = useMemo(() => parseCamera(params.get("v")), []); // eslint-disable-line react-hooks/exhaustive-deps

  const update = useCallback((changes: Changes) => {
    const next = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries(changes)) {
      next.delete(key);
      if (Array.isArray(value)) value.forEach((v) => next.append(key, v));
      else if (value !== null && value !== undefined) next.set(key, value);
    }
    // Next.js syncs useSearchParams with the native History API, without a navigation.
    window.history.replaceState(null, "", `?${next}`);
  }, []);

  return { selectedId, tags, basemap, initialCamera, update };
}
