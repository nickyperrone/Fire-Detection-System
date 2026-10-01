"use client";

import area from "@turf/area";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  TerraDraw,
  TerraDrawFreehandMode,
  TerraDrawPolygonMode,
  TerraDrawSelectMode,
  ValidateNotSelfIntersecting,
} from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";

import { simplifyRing } from "@/lib/geometry";

export type DrawnPolygon = { type: "Polygon"; coordinates: number[][][] };

/** "trace": drag a finger along the edge. "corners": tap each corner. */
export type DrawTool = "trace" | "corners";

const MODE: Record<DrawTool, string> = {
  trace: "freehand",
  corners: "polygon",
};

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
  /** The last shape was discarded because it was smaller than a field. */
  tooSmall: boolean;
};

// Half a hectare: smaller shapes are a slip of the finger, not a field.
const MIN_FIELD_HA = 0.5;
// A traced outline is simplified to about this many screen pixels, so few handles remain.
const TRACE_TOLERANCE_PX = 3;

function metersPerPixel(map: MapLibreMap): number {
  const latitude = (map.getCenter().lat * Math.PI) / 180;
  return (40_075_016.686 * Math.cos(latitude)) / (512 * 2 ** map.getZoom());
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
  const [tool, setToolState] = useState<DrawTool>("trace");
  const [tooSmall, setTooSmall] = useState(false);
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
    map.dragPan.disable();
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
    draw.on("change", (ids) => {
      setTooSmall(false);
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
        setTooSmall(true);
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
      closedIdRef.current = id;
      draw.setMode("select");
      draw.selectFeature(id);
      setTooSmall(false);
      setPolygon(shape);
      setHectares(area(shape) / 10_000);
    });
    return () => {
      draw.stop();
      drawRef.current = null;
      closedIdRef.current = null;
      map.dragPan.enable();
      map.doubleClickZoom.enable();
      setPolygon(null);
      setHectares(0);
    };
  }, [map, active]);

  const setTool = useCallback((next: DrawTool) => {
    setToolState(next);
    const draw = drawRef.current;
    if (draw && closedIdRef.current === null) draw.setMode(MODE[next]);
  }, []);

  const restart = useCallback(() => {
    const draw = drawRef.current;
    if (!draw) return;
    draw.setMode(MODE[toolRef.current]);
    draw.clear();
    closedIdRef.current = null;
    setPolygon(null);
    setHectares(0);
    setTooSmall(false);
  }, []);

  return { polygon, hectares, tool, setTool, restart, tooSmall };
}
