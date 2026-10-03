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
  hideTerritories,
  PARCELS_LAYER,
  RISK_LAYER,
  styleFor,
  TERRITORY_LAYERS,
} from "./overlay";

/** Changes once an hour, like the forecast it fetches. */
function hourVersion(): number {
  return Math.floor(Date.now() / 3_600_000);
}

/** Changes once a minute, so the lightning tile URL (and the browser cache) turns over. */
function lightningVersion(): number {
  return Math.floor(Date.now() / 60_000);
}

// Copied there by scripts/copy-maplibre-worker.mjs.
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

export type MapCamera = { lat: number; lon: number; zoom: number };

export type TerritoryState = { tone: Tone; dimmed: boolean; picked: boolean };

type Props = {
  basemap: Basemap;
  initialCamera: MapCamera;
  territoryStates: Map<number, TerritoryState>;
  /** Fields and lots the user hid; they are not drawn. */
  hiddenIds: Set<number>;
  territoriesVersion: number;
  selectedId: number | null;
  interactive: boolean;
  /** `additive` is true for Shift or Cmd clicks. */
  onSelect: (id: number | null, additive: boolean) => void;
  onCameraChange: (camera: MapCamera) => void;
  onReady: (map: MapLibreMap | null) => void;
  /** Texts for the fire popup, in the current language. */
  messages: Messages;
  showRisk: boolean;
  showParcels: boolean;
  /** The country's outline; while `grayOutside` is true everything else is grayed out. */
  boundary: CountryOutline | null;
  grayOutside: boolean;
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
      addOverlay(map, {
        basemap: latest.current.basemap,
        territoriesVersion: latest.current.territoriesVersion,
        lightningVersion: lightningVersion(),
        riskVersion: hourVersion(),
        showRisk: latest.current.showRisk,
        showParcels: latest.current.showParcels,
      });
      applyTerritoryStates(
        map,
        latest.current.territoryStates,
        latest.current.selectedId,
      );
      hideTerritories(map, [...latest.current.hiddenIds]);
      showOutsideMask(map, latest.current.boundary, latest.current.grayOutside);
    });
    map.on("click", (event) => handleClick(map, event, latest.current));
    for (const layer of [...TERRITORY_LAYERS, FIRE_LAYER]) {
      map.on(
        "mouseenter",
        layer,
        () => (map.getCanvas().style.cursor = "pointer"),
      );
      map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
    }
    map.on("moveend", () => {
      const center = map.getCenter();
      latest.current.onCameraChange({
        lat: center.lat,
        lon: center.lng,
        zoom: map.getZoom(),
      });
    });
    const stopPulse = pulseFires(map);
    // New flashes arrive every 20 s; ask for fresh lightning tiles once a minute.
    const lightningTimer = window.setInterval(() => {
      map
        .getSource<VectorTileSource>("lightning")
        ?.setTiles([tileUrl("lightning", lightningVersion())]);
    }, 60_000);
    onReady(map);
    return () => {
      stopPulse();
      window.clearInterval(lightningTimer);
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
    if (map?.isStyleLoaded())
      showOutsideMask(map, props.boundary, props.grayOutside);
  }, [props.boundary, props.grayOutside]);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.getLayer(PARCELS_LAYER)) {
      map.setLayoutProperty(
        PARCELS_LAYER,
        "visibility",
        props.showParcels ? "visible" : "none",
      );
    }
  }, [props.showParcels]);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.getLayer(RISK_LAYER)) {
      map.setLayoutProperty(
        RISK_LAYER,
        "visibility",
        props.showRisk ? "visible" : "none",
      );
    }
  }, [props.showRisk]);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.getSource("territories")) {
      applyTerritoryStates(map, props.territoryStates, props.selectedId);
    }
  }, [props.territoryStates, props.selectedId]);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.getLayer("field-fill")) hideTerritories(map, [...props.hiddenIds]);
  }, [props.hiddenIds]);

  // MapLibre's stylesheet makes its container position: relative, so the positioning lives on a
  // wrapper and the container only fills it.
  return (
    <div className="absolute inset-0">
      <div ref={container} className="h-full w-full" />
    </div>
  );
}

export type CountryOutline = GeoJSON.Feature<
  GeoJSON.Polygon | GeoJSON.MultiPolygon
>;

const OUTSIDE_SOURCE = "outside-country";

/** The whole world with the country cut out of it, so only the outside gets the gray. */
function outsideOf(country: CountryOutline): GeoJSON.Feature<GeoJSON.Polygon> {
  const world = [
    [-180, -85],
    [180, -85],
    [180, 85],
    [-180, 85],
    [-180, -85],
  ];
  const parts =
    country.geometry.type === "Polygon"
      ? [country.geometry.coordinates]
      : country.geometry.coordinates;
  return {
    type: "Feature",
    properties: {},
    geometry: {
      type: "Polygon",
      coordinates: [world, ...parts.map((polygon) => polygon[0])],
    },
  };
}

function showOutsideMask(
  map: MapLibreMap,
  country: CountryOutline | null,
  visible: boolean,
) {
  if (!country) return;
  if (!map.getSource(OUTSIDE_SOURCE)) {
    map.addSource(OUTSIDE_SOURCE, {
      type: "geojson",
      data: outsideOf(country),
    });
    map.addLayer({
      id: OUTSIDE_SOURCE,
      type: "fill",
      source: OUTSIDE_SOURCE,
      paint: { "fill-color": "#6b7280", "fill-opacity": 0.6 },
    });
  }
  map.setLayoutProperty(
    OUTSIDE_SOURCE,
    "visibility",
    visible ? "visible" : "none",
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
  const fires = map.queryRenderedFeatures(event.point, {
    layers: [FIRE_LAYER],
  });
  if (fires.length) {
    showFire(map, fires[0], event, props.messages);
    return;
  }
  // Sections are drawn above their field, so they come first when both are hit.
  const [territory] = map.queryRenderedFeatures(event.point, {
    layers: [...TERRITORY_LAYERS],
  });
  const additive = event.originalEvent.shiftKey || event.originalEvent.metaKey;
  props.onSelect(territory ? Number(territory.id) : null, additive);
}

function showFire(
  map: MapLibreMap,
  fire: MapGeoJSONFeature,
  event: MapMouseEvent,
  t: Messages,
) {
  const p = fire.properties;
  if (p.event_count !== undefined && p.event_count > 1) {
    map.easeTo({ center: event.lngLat, zoom: map.getZoom() + 2 });
    return;
  }
  const detected = formatAge(
    t,
    new Date(Number(p.last_detected_at) * 1000).toISOString(),
  );
  const content = document.createElement("div");
  content.className = "text-xs leading-5 text-slate-900";
  const title = document.createElement("strong");
  title.textContent = t.fire.popupTitle;
  const details = document.createElement("div");
  const confidence = p.confidence
    ? t.fire.confidence(t.confidence[p.confidence] ?? p.confidence)
    : "";
  details.textContent = [p.sensors, confidence, t.fire.detected(detected)]
    .filter(Boolean)
    .join(" · ");
  content.append(title, details);
  new Popup({ closeButton: false, maxWidth: "240px" })
    .setLngLat(event.lngLat)
    .setDOMContent(content)
    .addTo(map);
}

/** Slow breathing halo on fires, like a live location dot. Throttled to about 20 frames per second. */
function pulseFires(map: MapLibreMap): () => void {
  let frame = 0;
  let last = 0;
  const tick = (time: number) => {
    frame = requestAnimationFrame(tick);
    if (time - last < 50 || document.hidden || !map.getLayer(FIRE_HALO_LAYER))
      return;
    last = time;
    const phase = (Math.sin(time / 450) + 1) / 2;
    map.setPaintProperty(
      FIRE_HALO_LAYER,
      "circle-opacity",
      0.12 + phase * 0.25,
    );
  };
  frame = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(frame);
}
