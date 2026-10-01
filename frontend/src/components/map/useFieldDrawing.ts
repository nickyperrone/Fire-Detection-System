"use client";

import area from "@turf/area";
import type { Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  TerraDraw,
  TerraDrawFreehandMode,
  TerraDrawPolygonMode,
  TerraDrawSelectMode,
  ValidateNotSelfIntersecting,
} from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";

import { api } from "@/api/client";
import { simplifyRing } from "@/lib/geometry";

export type DrawnPolygon = { type: "Polygon"; coordinates: number[][][] };

/**
 * "parcel": tap an official parcel and use its outline (docs/08-cadastre.md).
 * "trace": drag a finger along the edge. "corners": tap each corner.
 */
export type DrawTool = "parcel" | "trace" | "corners";

const MODE: Record<DrawTool, string> = {
  // Terra Draw only shows the shape; taps are handled here, by asking for the parcel under them.
  parcel: "static",
  trace: "freehand",
  corners: "polygon",
};

export type Notice = "too_small" | "no_parcel";

const STYLE = {
  fillColor: "#22d3ee",
  fillOpacity: 0.2,
  outlineColor: "#22d3ee",
  outlineWidth: 2,
} as const;

export type FieldDrawing = {
  /** The closed polygon, kept up to date while its points are dragged. */
  polygon: DrawnPolygon | null;
  /** Area in hectares of the shape being drawn or edited. */
  hectares: number;
  tool: DrawTool;
  setTool: (tool: DrawTool) => void;
  /** Discards the shape and starts again with the current tool. */
  restart: () => void;
  /** Why the last tap or shape did not give a field, if it did not. */
  notice: Notice | null;
  /** Looking up the parcel under a tap. */
  searching: boolean;
  /** The official parcel the shape came from, when the parcel tool was used. */
  parcel: ParcelInfo | null;
};

export type ParcelInfo = {
  province: string;
  department: number;
  partida: number;
  plano: number | null;
};

// Half a hectare: smaller shapes are a slip of the finger, not a field.
const MIN_FIELD_HA = 0.5;
// A traced outline is simplified to about this many screen pixels, so few handles remain.
const TRACE_TOLERANCE_PX = 3;

function metersPerPixel(map: MapLibreMap): number {
  const latitude = (map.getCenter().lat * Math.PI) / 180;
  return (40_075_016.686 * Math.cos(latitude)) / (512 * 2 ** map.getZoom());
}

/** Panning stays on for the parcel tool (it only taps) and is off while tracing or tapping
 * corners, where a press that moves a few pixels would pan instead of drawing. */
function setPanning(map: MapLibreMap, tool: DrawTool) {
  if (tool === "parcel") map.dragPan.enable();
  else map.dragPan.disable();
}

/** A field is one polygon: the largest piece of the parcel, without holes. */
function outerShape(
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon,
): DrawnPolygon {
  const polygons =
    geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  const largest = polygons.reduce((best, next) =>
    area({ type: "Polygon", coordinates: next }) >
    area({ type: "Polygon", coordinates: best })
      ? next
      : best,
  );
  return { type: "Polygon", coordinates: [largest[0]] };
}

function buildDraw(map: MapLibreMap): TerraDraw {
  const editable = (midpoints: boolean) => ({
    feature: {
      validation: ValidateNotSelfIntersecting,
      coordinates: { draggable: true, deletable: true, midpoints },
    },
  });
  return new TerraDraw({
    adapter: new TerraDrawMapLibreGLAdapter({
      map,
      // Default is 8 px; taps on a phone in a moving truck drift more than that.
      minPixelDragDistanceDrawing: 20,
    }),
    modes: [
      // Press, drag along the edge, lift: the shape closes where the finger lifts.
      new TerraDrawFreehandMode({
        drawInteraction: "click-drag",
        minDistance: 6,
        styles: STYLE,
      }),
      new TerraDrawPolygonMode({
        validation: (feature) => ValidateNotSelfIntersecting(feature),
        styles: {
          ...STYLE,
          closingPointColor: "#ffffff",
          closingPointOutlineColor: "#22d3ee",
        },
      }),
      // After closing, every point can be dragged to fit the field edge exactly. A traced shape
      // has many points already, so it gets no midpoints.
      new TerraDrawSelectMode({
        allowManualDeselection: false,
        flags: { polygon: editable(true), freehand: editable(false) },
      }),
    ],
  });
}

/** Field drawing on the map while `active` is true. Leaving draw mode discards the shape. */
export function useFieldDrawing(
  map: MapLibreMap | null,
  active: boolean,
): FieldDrawing {
  const [polygon, setPolygon] = useState<DrawnPolygon | null>(null);
  const [hectares, setHectares] = useState(0);
  const [tool, setToolState] = useState<DrawTool>("parcel");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [searching, setSearching] = useState(false);
  const [parcel, setParcel] = useState<ParcelInfo | null>(null);
  const drawRef = useRef<TerraDraw | null>(null);
  const closedIdRef = useRef<string | number | null>(null);
  const toolRef = useRef(tool);
  useEffect(() => {
    toolRef.current = tool;
  });

  useEffect(() => {
    if (!map || !active) return;
    // While drawing, a press on the map always means drawing: with panning on, a tap that moves
    // a few pixels pans the map instead. Zoom still works; double-click zoom would fight with
    // closing the shape.
    // The parcel tool only taps, so the map can still be dragged to find the parcel.
    setPanning(map, toolRef.current);
    map.doubleClickZoom.disable();
    const draw = buildDraw(map);
    drawRef.current = draw;
    draw.start();
    draw.setMode(MODE[toolRef.current]);

    const polygonOf = (id: string | number): DrawnPolygon | null => {
      const feature = draw.getSnapshotFeature(id);
      return feature?.geometry.type === "Polygon"
        ? (feature.geometry as DrawnPolygon)
        : null;
    };
    const close = (id: string | number, shape: DrawnPolygon) => {
      closedIdRef.current = id;
      draw.setMode("select");
      draw.selectFeature(id);
      setNotice(null);
      setPolygon(shape);
      setHectares(area(shape) / 10_000);
    };

    const onTap = async (event: MapMouseEvent) => {
      if (toolRef.current !== "parcel" || closedIdRef.current !== null) return;
      setSearching(true);
      try {
        const found = await api.parcelAt(event.lngLat.lat, event.lngLat.lng);
        const shape = outerShape(found.geometry);
        const [added] = draw.addFeatures([
          { type: "Feature", geometry: shape, properties: { mode: "polygon" } },
        ]);
        if (!added.valid) throw new Error(added.reason);
        setParcel(found.properties as ParcelInfo);
        close(added.id as string | number, shape);
      } catch {
        setNotice("no_parcel");
      } finally {
        setSearching(false);
      }
    };
    map.on("click", onTap);

    draw.on("change", (ids) => {
      setNotice(null);
      const closedId = closedIdRef.current;
      const shape =
        closedId !== null
          ? polygonOf(closedId)
          : ids.map(polygonOf).find(Boolean);
      if (!shape) return;
      setHectares(area(shape) / 10_000);
      if (closedId !== null) setPolygon(shape);
    });
    draw.on("finish", (id, context) => {
      if (closedIdRef.current !== null || context.action !== "draw") return;
      let shape = polygonOf(id);
      if (!shape || area(shape) / 10_000 < MIN_FIELD_HA) {
        draw.clear();
        draw.setMode(MODE[toolRef.current]);
        setHectares(0);
        setNotice("too_small");
        return;
      }
      if (toolRef.current === "trace") {
        const ring = simplifyRing(
          shape.coordinates[0],
          TRACE_TOLERANCE_PX * metersPerPixel(map),
        );
        shape = { type: "Polygon", coordinates: [ring] };
        draw.updateFeatureGeometry(id, shape);
      }
      close(id, shape);
    });
    return () => {
      map.off("click", onTap);
      draw.stop();
      drawRef.current = null;
      closedIdRef.current = null;
      map.dragPan.enable();
      map.doubleClickZoom.enable();
      setPolygon(null);
      setHectares(0);
      setParcel(null);
      setNotice(null);
    };
  }, [map, active]);

  const setTool = useCallback(
    (next: DrawTool) => {
      setToolState(next);
      const draw = drawRef.current;
      if (draw && closedIdRef.current === null) {
        draw.setMode(MODE[next]);
        if (map) setPanning(map, next);
      }
    },
    [map],
  );

  const restart = useCallback(() => {
    const draw = drawRef.current;
    if (!draw) return;
    draw.setMode(MODE[toolRef.current]);
    draw.clear();
    closedIdRef.current = null;
    setPolygon(null);
    setHectares(0);
    setNotice(null);
    setParcel(null);
  }, []);

  return {
    polygon,
    hectares,
    tool,
    setTool,
    restart,
    notice,
    searching,
    parcel,
  };
}
