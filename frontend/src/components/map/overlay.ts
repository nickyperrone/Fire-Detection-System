import type {
  ExpressionSpecification,
  Map as MapLibreMap,
  StyleSpecification,
} from "maplibre-gl";

import { tileUrl } from "@/api/client";
import { TONE_HEX } from "@/lib/status";

export type Basemap = "dark" | "light" | "satellite";

export const BASEMAPS: Basemap[] = ["dark", "light", "satellite"];

const CARTO_GLYPHS =
  "https://tiles.basemaps.cartocdn.com/fonts/{fontstack}/{range}.pbf";
const LABEL_FONT = ["Montserrat Medium"];

const SATELLITE_STYLE: StyleSpecification = {
  version: 8,
  glyphs: CARTO_GLYPHS,
  sources: {
    imagery: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    },
  },
  layers: [{ id: "imagery", type: "raster", source: "imagery" }],
};

export function styleFor(basemap: Basemap): string | StyleSpecification {
  if (basemap === "satellite") return SATELLITE_STYLE;
  return basemap === "light"
    ? "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
    : "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
}

export const TERRITORY_LAYERS = ["section-fill", "field-fill"] as const;
export const FIRE_LAYER = "fire-core";
export const FIRE_HALO_LAYER = "fire-halo";
export const LIGHTNING_LAYER = "lightning-ring";
export const RISK_LAYER = "risk-fill";
export const PARCELS_LAYER = "parcel-line";

// Set per field by the app: its status tone, or its tag color when coloring by tags.
const territoryColor: ExpressionSpecification = [
  "coalesce",
  ["feature-state", "color"],
  TONE_HEX.unknown,
];

const highlighted: ExpressionSpecification = [
  "any",
  ["boolean", ["feature-state", "selected"], false],
  ["boolean", ["feature-state", "picked"], false],
];

function fillOpacity(base: number): ExpressionSpecification {
  return [
    "case",
    highlighted,
    base + 0.1,
    ["boolean", ["feature-state", "dimmed"], false],
    base / 4,
    base,
  ];
}

const lineOpacity: ExpressionSpecification = [
  "case",
  ["boolean", ["feature-state", "dimmed"], false],
  0.3,
  1,
];

const byKind = (kind: string): ExpressionSpecification => [
  "==",
  ["get", "kind"],
  kind,
];

const TERRITORY_KIND_BY_LAYER = {
  "field-fill": "FIELD",
  "section-fill": "SECTION",
  "field-line": "FIELD",
  "section-line": "SECTION",
  "field-label": "FIELD",
  "section-label": "SECTION",
} as const;

/** Leaves the given fields and lots off the map. A filter, not feature state, because the
 * labels are another tile layer and filters also stop them from taking label space. */
export function hideTerritories(map: MapLibreMap, ids: number[]): void {
  for (const [layer, kind] of Object.entries(TERRITORY_KIND_BY_LAYER)) {
    map.setFilter(
      layer,
      ids.length
        ? ["all", byKind(kind), ["!", ["in", ["id"], ["literal", ids]]]]
        : byKind(kind),
    );
  }
}

const isCluster: ExpressionSpecification = ["has", "event_count"];

export type OverlayOptions = {
  basemap: Basemap;
  /** Bumped after a field changes, so its tiles are fetched again. */
  territoriesVersion: number;
  lightningVersion: number;
  riskVersion: number;
  showRisk: boolean;
  showParcels: boolean;
};

/** Adds our sources and layers on top of the current basemap. Called again after every style change. */
export function addOverlay(map: MapLibreMap, options: OverlayOptions): void {
  const { territoriesVersion, lightningVersion, riskVersion, showRisk } =
    options;
  // Below everything else: the risk shading is background, fields and fires sit on top.
  map.addSource("risk", {
    type: "vector",
    tiles: [tileUrl("risk", riskVersion)],
    maxzoom: 10,
  });
  map.addLayer({
    id: RISK_LAYER,
    type: "fill",
    source: "risk",
    "source-layer": "risk",
    layout: { visibility: showRisk ? "visible" : "none" },
    paint: {
      "fill-color": TONE_HEX.bad,
      // Transparent at low risk, stronger red as the next-day probability grows.
      "fill-opacity": [
        "interpolate",
        ["linear"],
        ["get", "probability"],
        0.02,
        0,
        0.05,
        0.12,
        0.35,
        0.5,
      ],
      "fill-antialias": false,
    },
  });
  // Property lines (docs/08-cadastre.md): thin, light on dark and satellite, dark on light.
  map.addSource("parcels", {
    type: "vector",
    tiles: [tileUrl("parcels")],
    minzoom: 13,
    maxzoom: 16,
    // IDECOR publishes under CC BY-SA 4.0, which asks for credit where the data is shown.
    attribution:
      "Cadastre: ATER Entre Ríos, ARBA Buenos Aires, IDECOR Córdoba (CC BY-SA 4.0)",
  });
  map.addLayer({
    id: PARCELS_LAYER,
    type: "line",
    source: "parcels",
    "source-layer": "parcels",
    layout: { visibility: options.showParcels ? "visible" : "none" },
    paint: {
      "line-color": options.basemap === "light" ? "#475569" : "#e5e7eb",
      "line-opacity": 0.6,
      "line-width": ["interpolate", ["linear"], ["zoom"], 13, 0.5, 17, 1.4],
    },
  });
  map.addSource("territories", {
    type: "vector",
    tiles: [tileUrl("territories", territoriesVersion)],
    maxzoom: 16,
  });
  map.addSource("fires", {
    type: "vector",
    tiles: [tileUrl("fire_events")],
    maxzoom: 14,
  });
  map.addSource("lightning", {
    type: "vector",
    tiles: [tileUrl("lightning", lightningVersion)],
    maxzoom: 14,
  });
  map.addSource("observations", {
    type: "vector",
    tiles: [tileUrl("observations")],
    minzoom: 11,
    maxzoom: 14,
  });

  map.addLayer({
    id: "field-fill",
    type: "fill",
    source: "territories",
    "source-layer": "territories",
    filter: byKind("FIELD"),
    paint: { "fill-color": territoryColor, "fill-opacity": fillOpacity(0.18) },
  });
  map.addLayer({
    id: "section-fill",
    type: "fill",
    source: "territories",
    "source-layer": "territories",
    filter: byKind("SECTION"),
    paint: { "fill-color": territoryColor, "fill-opacity": fillOpacity(0.12) },
  });
  map.addLayer({
    id: "field-line",
    type: "line",
    source: "territories",
    "source-layer": "territories",
    filter: byKind("FIELD"),
    paint: {
      "line-color": territoryColor,
      "line-width": ["case", highlighted, 3.5, 2],
      "line-opacity": lineOpacity,
    },
  });
  map.addLayer({
    id: "section-line",
    type: "line",
    source: "territories",
    "source-layer": "territories",
    filter: byKind("SECTION"),
    paint: {
      "line-color": territoryColor,
      "line-width": 1.2,
      "line-dasharray": [2, 2],
      "line-opacity": lineOpacity,
    },
  });
  const labelPaint = {
    "text-color": "#f3f6fa",
    "text-halo-color": "#0b0e13",
    "text-halo-width": 1.4,
  };
  // Field names while the field is small on screen, lot names once the lots are readable.
  map.addLayer({
    id: "field-label",
    type: "symbol",
    source: "territories",
    "source-layer": "territory_labels",
    filter: byKind("FIELD"),
    minzoom: 10,
    maxzoom: 13,
    layout: {
      "text-field": ["get", "name"],
      "text-font": LABEL_FONT,
      "text-size": 13,
    },
    paint: labelPaint,
  });
  map.addLayer({
    id: "section-label",
    type: "symbol",
    source: "territories",
    "source-layer": "territory_labels",
    filter: byKind("SECTION"),
    minzoom: 13,
    layout: {
      "text-field": ["get", "name"],
      "text-font": LABEL_FONT,
      "text-size": 12,
    },
    paint: labelPaint,
  });

  map.addLayer({
    id: "observation-dot",
    type: "circle",
    source: "observations",
    "source-layer": "observations",
    paint: {
      "circle-radius": 3,
      "circle-color": TONE_HEX.bad,
      "circle-stroke-color": "#0b0e13",
      "circle-stroke-width": 1,
    },
  });
  // Lightning as red rings, so they read apart from fires (filled dots); older flashes fade.
  map.addLayer({
    id: LIGHTNING_LAYER,
    type: "circle",
    source: "lightning",
    "source-layer": "lightning",
    paint: {
      "circle-radius": 5,
      "circle-color": "rgba(0,0,0,0)",
      "circle-stroke-color": TONE_HEX.bad,
      "circle-stroke-width": 2,
      "circle-stroke-opacity": [
        "interpolate",
        ["linear"],
        ["get", "age_minutes"],
        0,
        1,
        60,
        0.2,
      ],
    },
  });
  map.addLayer({
    id: FIRE_HALO_LAYER,
    type: "circle",
    source: "fires",
    "source-layer": "fire_events",
    paint: {
      "circle-radius": ["case", isCluster, 22, 14],
      "circle-color": TONE_HEX.bad,
      "circle-opacity": 0.25,
      "circle-blur": 0.6,
    },
  });
  map.addLayer({
    id: FIRE_LAYER,
    type: "circle",
    source: "fires",
    "source-layer": "fire_events",
    paint: {
      "circle-radius": [
        "case",
        isCluster,
        [
          "interpolate",
          ["linear"],
          ["get", "event_count"],
          1,
          8,
          10,
          13,
          50,
          18,
        ],
        6,
      ],
      "circle-color": TONE_HEX.bad,
      // Lower confidence is paler, still red: the text says how sure it is.
      "circle-opacity": [
        "case",
        [
          "any",
          ["==", ["get", "confidence"], "high"],
          ["to-boolean", ["get", "any_high_confidence"]],
        ],
        1,
        0.65,
      ],
      "circle-stroke-color": "#fff4e6",
      "circle-stroke-width": 1.5,
    },
  });
  map.addLayer({
    id: "fire-count",
    type: "symbol",
    source: "fires",
    "source-layer": "fire_events",
    filter: ["all", isCluster, [">", ["get", "event_count"], 1]],
    layout: {
      "text-field": ["to-string", ["get", "event_count"]],
      "text-font": LABEL_FONT,
      "text-size": 11,
      "text-allow-overlap": true,
    },
    paint: { "text-color": "#ffffff" },
  });
}
