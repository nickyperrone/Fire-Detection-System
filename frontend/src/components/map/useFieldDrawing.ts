"use client";

import area from "@turf/area";
import type { Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  TerraDraw,
  TerraDrawFreehandMode,
  TerraDrawPolygonMode,
  TerraDrawModeUndoRedo,
  TerraDrawSelectMode,
  TerraDrawUndoRedoKeyboardShortcuts,
  ValidateNotSelfIntersecting,
} from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";

import { api, ApiError } from "@/api/client";
import { simplifyRing } from "@/lib/geometry";

export type DrawnPolygon = { type: "Polygon"; coordinates: number[][][] };

/**
 * "parcel": tap an official parcel and use its outline (docs/08-cadastre.md).
 * "detect": tap a field and find its outline in satellite images (docs/10-field-detection.md).
 * "trace": drag a finger along the edge. "corners": tap each corner.
 */
export type DrawTool = "parcel" | "detect" | "trace" | "corners";

const MODE: Record<DrawTool, string> = {
  // Terra Draw only shows the shape; taps are handled here, by asking the API for an outline.
  parcel: "static",
  detect: "static",
  trace: "freehand",
  corners: "polygon",
};

const TAP_TOOLS: DrawTool[] = ["parcel", "detect"];

export type Notice =
  "too_small" | "no_parcel" | "no_field_found" | "no_images" | "detect_failed";

/** Where a detected outline came from: how many clear Sentinel-2 dates, and their range. */
export type DetectInfo = { dates: number; first: string; last: string };

/** A hand-drawn shape fitted to the property lines (docs/08-cadastre.md#in-the-map). */
export type Fit = {
  method: "parcels" | "edges";
  /** Parcels the field became, for the "parcels" method. */
  parcels: number;
  /** Whether the map shows the fitted shape (true) or the drawing as it was made. */
  applied: boolean;
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
  /** Why the last tap or shape did not give a field, if it did not. */
  notice: Notice | null;
  /** Looking up the parcel, or detecting the field, under a tap. */
  searching: boolean;
  /** Set when the outline was found in satellite images by the detect tool. */
  detected: DetectInfo | null;
  /** The official parcel the shape came from: the one tapped, or the only one it was fitted to. */
  parcel: ParcelInfo | null;
  /** Asking the server to fit a closed hand-drawn shape to the property lines. */
  fitting: boolean;
  fit: Fit | null;
  /** Switches between the fitted shape and the drawing as it was made. */
  toggleFit: () => void;
  /** Corners placed so far with the corners tool, before the shape is closed. */
  corners: number;
  /** Takes back the last corner placed. */
  undoCorner: () => void;
  /** Closes the shape on the corners placed, as tapping the first corner again does. */
  closeCorners: () => void;
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

/** Panning is off only while tracing, where every drag draws. Tapping corners leaves it on:
 * a drag moves the map to reach the next corner, a tap places one. */
function setPanning(map: MapLibreMap, tool: DrawTool) {
  if (tool === "trace") map.dragPan.disable();
  else map.dragPan.enable();
}

// Terra Draw closes a polygon being drawn on this key, received by the map's canvas.
const FINISH_KEY = "Enter";

/** Corners committed so far on a polygon still being drawn. */
function cornersDrawn(draw: TerraDraw): number {
  const drawing = draw
    .getSnapshot()
    .find(
      (f) => f.properties.mode === "polygon" && f.properties.currentlyDrawing,
    );
  const count = drawing?.properties.committedCoordinateCount;
  return typeof count === "number" ? count : 0;
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

/** Puts one version of a fitted shape on the map. Points dragged since are replaced. */
function showShape(
  draw: TerraDraw,
  id: string | number,
  fitted: boolean,
  shapes: { drawn: DrawnPolygon; fitted: DrawnPolygon },
) {
  // The selection handles belong to the old geometry; reselecting rebuilds them.
  draw.deselectFeature(id);
  draw.updateFeatureGeometry(id, fitted ? shapes.fitted : shapes.drawn);
  draw.selectFeature(id);
}

function buildDraw(map: MapLibreMap): TerraDraw {
  const editable = (midpoints: boolean) => ({
    feature: {
      validation: ValidateNotSelfIntersecting,
      coordinates: { draggable: true, deletable: true, midpoints },
    },
  });
  return new TerraDraw({
    // Undo takes back the last corner while drawing (also Cmd or Ctrl+Z).
    undoRedo: {
      modeLevel: new TerraDrawModeUndoRedo(),
      keyboardShortcuts: new TerraDrawUndoRedoKeyboardShortcuts(),
    },
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
  const [detected, setDetected] = useState<DetectInfo | null>(null);
  const [parcel, setParcel] = useState<ParcelInfo | null>(null);
  const [fitting, setFitting] = useState(false);
  const [fit, setFit] = useState<Fit | null>(null);
  const [corners, setCorners] = useState(0);
  // Both versions of a fitted shape, so either can be put back.
  const shapesRef = useRef<{
    drawn: DrawnPolygon;
    fitted: DrawnPolygon;
    parcel: ParcelInfo | null;
  } | null>(null);
  const drawRef = useRef<TerraDraw | null>(null);
  const closedIdRef = useRef<string | number | null>(null);
  const toolRef = useRef(tool);
  useEffect(() => {
    toolRef.current = tool;
  });

  useEffect(() => {
    if (!map || !active) return;
    const startDrawing = (): (() => void) => {
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

      const fitToPropertyLines = async (
        id: string | number,
        drawn: DrawnPolygon,
      ) => {
        setFitting(true);
        try {
          const result = await api.snap(drawn);
          // The shape may have been discarded while the server answered.
          if (closedIdRef.current !== id || result.method === "none") return;
          const parcels = result.parcels as ParcelInfo[];
          shapesRef.current = {
            drawn,
            fitted: result.geometry as DrawnPolygon,
            parcel: parcels.length === 1 ? parcels[0] : null,
          };
          showShape(draw, id, true, shapesRef.current);
          setParcel(shapesRef.current.parcel);
          setFit({
            method: result.method as Fit["method"],
            parcels: parcels.length,
            applied: true,
          });
        } catch {
          // Fitting is a convenience: without it the drawing stays as it was made.
        } finally {
          setFitting(false);
        }
      };

      const show = (shape: DrawnPolygon) => {
        const [added] = draw.addFeatures([
          { type: "Feature", geometry: shape, properties: { mode: "polygon" } },
        ]);
        if (!added.valid) throw new Error(added.reason);
        close(added.id as string | number, shape);
      };

      const onTap = async (event: MapMouseEvent) => {
        const tool = toolRef.current;
        if (!TAP_TOOLS.includes(tool) || closedIdRef.current !== null) return;
        const { lat, lng } = event.lngLat;
        setNotice(null);
        setSearching(true);
        try {
          if (tool === "parcel") {
            const found = await api.parcelAt(lat, lng);
            setParcel(found.properties as ParcelInfo);
            show(outerShape(found.geometry));
          } else {
            const found = await api.detectField(lat, lng);
            setDetected({
              dates: found.dates,
              first: found.first,
              last: found.last,
            });
            show(found.geometry as DrawnPolygon);
          }
        } catch (error) {
          const code = error instanceof ApiError ? error.code : null;
          setNotice(
            tool === "parcel"
              ? "no_parcel"
              : code === "no_field_found" || code === "no_images"
                ? code
                : "detect_failed",
          );
        } finally {
          setSearching(false);
        }
      };
      map.on("click", onTap);

      draw.on("change", (ids) => {
        setNotice(null);
        if (closedIdRef.current === null) setCorners(cornersDrawn(draw));
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
        setCorners(0);
        close(id, shape);
        void fitToPropertyLines(id, shape);
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
        setDetected(null);
        setNotice(null);
        setFit(null);
        setFitting(false);
        setCorners(0);
        shapesRef.current = null;
      };
    };
    let stopDrawing: (() => void) | null = null;
    const start = () => {
      stopDrawing = startDrawing();
    };
    // Terra Draw adds layers to the style, so it waits when "+" is tapped while the style loads.
    // Not "idle": a pulsing fire keeps the map repainting, and idle would never come. Our own
    // sources are added on style load, so their presence means the style is ready.
    if (map.getSource("territories")) start();
    else map.once("style.load", start);
    return () => {
      map.off("style.load", start);
      stopDrawing?.();
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
    setDetected(null);
    setFit(null);
    setCorners(0);
    shapesRef.current = null;
  }, []);

  const undoCorner = useCallback(() => {
    const draw = drawRef.current;
    if (!draw?.canUndo()) return;
    draw.undo();
    setCorners(cornersDrawn(draw));
  }, []);

  const closeCorners = useCallback(() => {
    map
      ?.getCanvas()
      .dispatchEvent(new KeyboardEvent("keyup", { key: FINISH_KEY }));
  }, [map]);

  const toggleFit = useCallback(() => {
    const draw = drawRef.current;
    const id = closedIdRef.current;
    const shapes = shapesRef.current;
    if (!draw || id === null || !shapes) return;
    setFit((current) => {
      if (!current) return current;
      const applied = !current.applied;
      showShape(draw, id, applied, shapes);
      setParcel(applied ? shapes.parcel : null);
      return { ...current, applied };
    });
  }, []);

  return {
    polygon,
    hectares,
    tool,
    setTool,
    restart,
    notice,
    searching,
    detected,
    parcel,
    fitting,
    fit,
    toggleFit,
    corners,
    undoCorner,
    closeCorners,
  };
}
