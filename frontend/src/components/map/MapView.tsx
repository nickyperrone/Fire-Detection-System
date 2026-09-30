"use client";

import {
  AttributionControl,
  Map as MapLibreMap,
  Popup,
  type MapGeoJSONFeature,
  type MapMouseEvent,
  setWorkerUrl,
  type VectorTileSource,
} from "maplibre-gl";
import { useEffect, useRef } from "react";

import { tileUrl } from "@/api/client";
import type { Messages } from "@/i18n/messages";
import { formatAge } from "@/i18n/text";
import type { Tone } from "@/lib/status";

import {
  addOverlay,
  type Basemap,
  FIRE_HALO_LAYER,
  FIRE_LAYER,
  styleFor,
  TERRITORY_LAYERS,
} from "./overlay";

// Copied there by scripts/copy-maplibre-worker.mjs.
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

export type MapCamera = { lat: number; lon: number; zoom: number };

export type TerritoryState = { tone: Tone; dimmed: boolean; picked: boolean };

type Props = {
  basemap: Basemap;
  initialCamera: MapCamera;
  territoryStates: Map<number, TerritoryState>;
  territoriesVersion: number;
  selectedId: number | null;
  interactive: boolean;
  /** `additive` is true for Shift or Cmd clicks. */
  onSelect: (id: number | null, additive: boolean) => void;
  onCameraChange: (camera: MapCamera) => void;
  onReady: (map: MapLibreMap | null) => void;
  /** Texts for the fire popup, in the current language. */
  messages: Messages;
};

export function MapView(props: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const shownBasemap = useRef(props.basemap);
  // Handlers registered once on the map read the latest props through this ref.
  const latest = useRef(props);
  useEffect(() => {
    latest.current = props;
  });

  useEffect(() => {
    const { basemap, initialCamera, onReady } = latest.current;
    const map = new MapLibreMap({
      container: container.current!,
      style: styleFor(basemap),
      center: [initialCamera.lon, initialCamera.lat],
      zoom: initialCamera.zoom,
      attributionControl: false,
      // Always north-up and flat, like a paper map of the fields: no gesture or key can
      // rotate or tilt it.
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      maxPitch: 0,
    });
    mapRef.current = map;
    map.addControl(new AttributionControl({ compact: true }), "bottom-left");
    map.touchZoomRotate.disableRotation();
    map.keyboard.disableRotation();

    map.on("style.load", () => {
      addOverlay(map, latest.current.territoriesVersion);
      applyTerritoryStates(map, latest.current.territoryStates, latest.current.selectedId);
    });
    map.on("click", (event) => handleClick(map, event, latest.current));
    for (const layer of [...TERRITORY_LAYERS, FIRE_LAYER]) {
      map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
    }
    map.on("moveend", () => {
      const center = map.getCenter();
      latest.current.onCameraChange({ lat: center.lat, lon: center.lng, zoom: map.getZoom() });
    });
    const stopPulse = pulseFires(map);
    onReady(map);
    return () => {
      stopPulse();
      onReady(null);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (props.basemap === shownBasemap.current) return;
    shownBasemap.current = props.basemap;
    // setStyle drops our sources; the style.load handler adds them back.
    mapRef.current?.setStyle(styleFor(props.basemap));
  }, [props.basemap]);

  useEffect(() => {
    // A new version in the URL makes MapLibre and the browser cache fetch fresh field tiles.
    mapRef.current
      ?.getSource<VectorTileSource>("territories")
      ?.setTiles([tileUrl("territories", props.territoriesVersion)]);
  }, [props.territoriesVersion]);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.getSource("territories")) {
      applyTerritoryStates(map, props.territoryStates, props.selectedId);
    }
  }, [props.territoryStates, props.selectedId]);

  // MapLibre's stylesheet makes its container position: relative, so the positioning lives on a
  // wrapper and the container only fills it.
  return (
    <div className="absolute inset-0">
      <div ref={container} className="h-full w-full" />
    </div>
  );
}

function applyTerritoryStates(
  map: MapLibreMap,
  states: Map<number, TerritoryState>,
  selectedId: number | null,
): void {
  map.removeFeatureState({ source: "territories", sourceLayer: "territories" });
  for (const [id, state] of states) {
    map.setFeatureState(
      { source: "territories", sourceLayer: "territories", id },
      { ...state, selected: id === selectedId },
    );
  }
}

function handleClick(map: MapLibreMap, event: MapMouseEvent, props: Props) {
  if (!props.interactive) return;
  const fires = map.queryRenderedFeatures(event.point, { layers: [FIRE_LAYER] });
  if (fires.length) {
    showFire(map, fires[0], event, props.messages);
    return;
  }
  // Sections are drawn above their field, so they come first when both are hit.
  const [territory] = map.queryRenderedFeatures(event.point, { layers: [...TERRITORY_LAYERS] });
  const additive = event.originalEvent.shiftKey || event.originalEvent.metaKey;
  props.onSelect(territory ? Number(territory.id) : null, additive);
}

function showFire(map: MapLibreMap, fire: MapGeoJSONFeature, event: MapMouseEvent, t: Messages) {
  const p = fire.properties;
  if (p.event_count !== undefined && p.event_count > 1) {
    map.easeTo({ center: event.lngLat, zoom: map.getZoom() + 2 });
    return;
  }
  const detected = formatAge(t, new Date(Number(p.last_detected_at) * 1000).toISOString());
  const content = document.createElement("div");
  content.className = "text-xs leading-5 text-slate-900";
  const title = document.createElement("strong");
  title.textContent = t.fire.popupTitle;
  const details = document.createElement("div");
  const confidence = p.confidence ? t.fire.confidence(t.confidence[p.confidence] ?? p.confidence) : "";
  details.textContent = [p.sensors, confidence, t.fire.detected(detected)]
    .filter(Boolean)
    .join(" · ");
  content.append(title, details);
  new Popup({ closeButton: false, maxWidth: "240px" }).setLngLat(event.lngLat).setDOMContent(content).addTo(map);
}

/** Slow breathing halo on fires, like a live location dot. Throttled to about 20 frames per second. */
function pulseFires(map: MapLibreMap): () => void {
  let frame = 0;
  let last = 0;
  const tick = (time: number) => {
    frame = requestAnimationFrame(tick);
    if (time - last < 50 || document.hidden || !map.getLayer(FIRE_HALO_LAYER)) return;
    last = time;
    const phase = (Math.sin(time / 450) + 1) / 2;
    map.setPaintProperty(FIRE_HALO_LAYER, "circle-opacity", 0.12 + phase * 0.25);
  };
  frame = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(frame);
}
