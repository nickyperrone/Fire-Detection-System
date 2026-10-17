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
import {
  type DrawTool,
  type EditMode,
  type History,
  popped,
  pushed,
} from "@/lib/drawStep";
import { insideRing, simplifyRing } from "@/lib/geometry";
import {
  addPiece,
  clipTo,
  type EditNote,
  removePiece,
  type Shape,
} from "@/lib/shapeOps";

import { PARCELS_MIN_ZOOM } from "./overlay";

export type DrawnPolygon = { type: "Polygon"; coordinates: number[][][] };

export type { DrawTool, EditMode };

const MODE: Record<DrawTool, string> = {
  // Terra Draw only shows the shape; taps are handled here, by asking the API for an outline.
  parcel: "static",
  detect: "static",
  trace: "freehand",
  corners: "polygon",
};

const TAP_TOOLS: DrawTool[] = ["parcel", "detect"];

export type Notice =
  | "too_small"
  | "no_parcel"
  | "no_field_found"
  | "no_images"
  | "detect_failed"
  | "outside_parent";

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

// A zone added or taken out smaller than this is a slip of the finger.
const MIN_PIECE_HA = 0.05;

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
  /** The map is close enough to see property lines and pick a field. */
  closeEnough: boolean;
  /** What a drawn shape is being used for: moving its corners, or drawing a zone to add or
   * take out. Only with a shape on the map. */
  mode: EditMode;
  setMode: (mode: EditMode) => void;
  /** Takes back the last change to the shape. */
  undo: () => void;
  canUndo: boolean;
  /** What the last edit had to do ("kept the biggest piece", "cut to the field"), if anything. */
  note: EditNote | null;
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
  /** A lot is cut to the edge of its field. */
  parent: GeoJSON.Polygon | GeoJSON.MultiPolygon | null = null,
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
  const [zoom, setZoom] = useState(() => map?.getZoom() ?? 0);
  const [mode, setModeState] = useState<EditMode>("move");
  const [history, setHistory] = useState<History>([]);
  const [note, setNote] = useState<EditNote | null>(null);
  // Both versions of a fitted shape, so either can be put back.
  const shapesRef = useRef<{
    drawn: DrawnPolygon;
    fitted: DrawnPolygon;
    parcel: ParcelInfo | null;
  } | null>(null);
  const drawRef = useRef<TerraDraw | null>(null);
  const closedIdRef = useRef<string | number | null>(null);
  const toolRef = useRef(tool);
  const modeRef = useRef(mode);
  const parentRef = useRef(parent);
  // The shape as of the last change, to put on the history when the next one is made.
  const lastRef = useRef<Shape | null>(null);
  const historyRef = useRef<History>([]);
  useEffect(() => {
    toolRef.current = tool;
    modeRef.current = mode;
    parentRef.current = parent;
    historyRef.current = history;
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
      const resetEdits = () => {
        historyRef.current = [];
        setHistory([]);
        lastRef.current = null;
        setNote(null);
        modeRef.current = "move";
        setModeState("move");
      };

      const close = (id: string | number, shape: DrawnPolygon) => {
        closedIdRef.current = id;
        lastRef.current = shape;
        draw.setMode("select");
        draw.selectFeature(id);
        setNotice(null);
        setPolygon(shape);
        setHectares(area(shape) / 10_000);
      };

      // A shape just marked becomes the one to adjust. A lot is cut to its field first.
      const accept = (id: string | number, shape: DrawnPolygon): boolean => {
        const field = parentRef.current;
        setNote(null);
        let kept = shape;
        if (field) {
          const result = clipTo(shape, field);
          if (!result.shape) {
            draw.clear();
            draw.setMode(MODE[toolRef.current]);
            setHectares(0);
            setNotice("outside_parent");
            return false;
          }
          kept = result.shape;
          if (result.note) {
            draw.updateFeatureGeometry(id, kept);
            setNote(result.note);
          }
        }
        close(id, kept);
        return true;
      };

      // Puts a new geometry on the shape being adjusted, with its corner handles rebuilt.
      const replaceShape = (id: string | number, shape: DrawnPolygon) => {
        draw.setMode("select");
        try {
          draw.deselectFeature(id);
        } catch {
          // It was not selected.
        }
        draw.updateFeatureGeometry(id, shape);
        draw.selectFeature(id);
        lastRef.current = shape;
        setPolygon(shape);
        setHectares(area(shape) / 10_000);
      };

      // A zone was drawn (or tapped) to add to the shape or take out of it.
      const applyPiece = (piece: DrawnPolygon | null) => {
        const id = closedIdRef.current;
        const base = id !== null ? polygonOf(id) : null;
        const resume = () => {
          draw.setMode(MODE[toolRef.current]);
          setCorners(0);
        };
        if (
          id === null ||
          !base ||
          !piece ||
          area(piece) / 10_000 < MIN_PIECE_HA
        ) {
          resume();
          setNotice("too_small");
          return;
        }
        let result =
          modeRef.current === "add"
            ? addPiece(base, piece)
            : removePiece(base, piece);
        if (result.shape && parentRef.current) {
          const clipped = clipTo(result.shape, parentRef.current);
          if (clipped.shape) {
            result = {
              shape: clipped.shape,
              note: clipped.note ?? result.note,
            };
          }
        }
        if (!result.shape) {
          resume();
          setNote(result.note);
          return;
        }
        // The fit to property lines described the shape as it was.
        try {
          replaceShape(id, result.shape);
        } catch {
          // The drawing layer would not take it: the shape stays as it was.
          resume();
          setNote("unusable");
          return;
        }
        shapesRef.current = null;
        setFit(null);
        const next = pushed(historyRef.current, base);
        historyRef.current = next;
        setHistory(next);
        setNote(result.note);
        modeRef.current = "move";
        setModeState("move");
        map.dragPan.enable();
        setCorners(0);
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
          lastRef.current = shapesRef.current.fitted;
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
        accept(added.id as string | number, shape);
      };

      const onTap = async (event: MapMouseEvent) => {
        const tool = toolRef.current;
        if (!TAP_TOOLS.includes(tool)) return;
        const { lat, lng } = event.lngLat;
        const closedId = closedIdRef.current;
        // With a shape on the map, taps draw a zone to add; taking one out has no parcel to tap.
        const zone = closedId !== null && modeRef.current !== "move";
        if (zone && modeRef.current === "remove") return;
        if (closedId !== null && !zone) {
          // A tap inside the shape is for adjusting it; outside, another parcel or field takes
          // its place, as if "Empezar de nuevo" had been tapped first.
          const shape = polygonOf(closedId);
          if (!shape || insideRing([lng, lat], shape.coordinates[0])) return;
          draw.setMode(MODE[tool]);
          draw.clear();
          closedIdRef.current = null;
          setPolygon(null);
          setHectares(0);
          setParcel(null);
          setDetected(null);
          setFit(null);
          shapesRef.current = null;
          resetEdits();
        }
        setNotice(null);
        setNote(null);
        setSearching(true);
        try {
          let shape: DrawnPolygon;
          if (tool === "parcel") {
            const found = await api.parcelAt(lat, lng);
            if (!zone) setParcel(found.properties as ParcelInfo);
            shape = outerShape(found.geometry);
          } else {
            const found = await api.detectField(lat, lng);
            if (!zone) {
              setDetected({
                dates: found.dates,
                first: found.first,
                last: found.last,
              });
            }
            shape = found.geometry as DrawnPolygon;
          }
          if (zone) applyPiece(shape);
          else show(shape);
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
        const closedId = closedIdRef.current;
        if (closedId === null || modeRef.current !== "move") {
          setCorners(cornersDrawn(draw));
        }
        const shape =
          closedId !== null
            ? polygonOf(closedId)
            : ids.map(polygonOf).find(Boolean);
        if (!shape) return;
        setHectares(area(shape) / 10_000);
        if (closedId !== null) setPolygon(shape);
      });

      // A traced outline has a point every few pixels: keep the ones that matter.
      const simplified = (shape: DrawnPolygon): DrawnPolygon => {
        if (toolRef.current !== "trace") return shape;
        const ring = simplifyRing(
          shape.coordinates[0],
          TRACE_TOLERANCE_PX * metersPerPixel(map),
        );
        return { type: "Polygon", coordinates: [ring] };
      };

      draw.on("finish", (id, context) => {
        const closedId = closedIdRef.current;
        if (closedId !== null) {
          if (context.action === "draw") {
            if (modeRef.current === "move") return;
            const piece = polygonOf(id);
            draw.removeFeatures([id]);
            applyPiece(piece && simplified(piece));
            return;
          }
          // A corner or the whole shape was dragged: the shape before it can be put back.
          const now = polygonOf(closedId);
          const before = lastRef.current;
          if (
            now &&
            before &&
            JSON.stringify(now.coordinates) !==
              JSON.stringify(before.coordinates)
          ) {
            const next = pushed(historyRef.current, before);
            historyRef.current = next;
            setHistory(next);
          }
          lastRef.current = now;
          return;
        }
        if (context.action !== "draw") return;
        let shape = polygonOf(id);
        if (!shape || area(shape) / 10_000 < MIN_FIELD_HA) {
          draw.clear();
          draw.setMode(MODE[toolRef.current]);
          setHectares(0);
          setNotice("too_small");
          return;
        }
        if (toolRef.current === "trace") {
          shape = simplified(shape);
          draw.updateFeatureGeometry(id, shape);
        }
        setCorners(0);
        if (accept(id, shape))
          void fitToPropertyLines(id, polygonOf(id) ?? shape);
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
        resetEdits();
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

  useEffect(() => {
    if (!map) return;
    const update = () => setZoom(map.getZoom());
    update();
    map.on("zoomend", update);
    return () => {
      map.off("zoomend", update);
    };
  }, [map]);

  const setTool = useCallback(
    (next: DrawTool) => {
      setToolState(next);
      const draw = drawRef.current;
      if (
        draw &&
        (closedIdRef.current === null || modeRef.current !== "move")
      ) {
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
    historyRef.current = [];
    setHistory([]);
    lastRef.current = null;
    setNote(null);
    modeRef.current = "move";
    setModeState("move");
  }, []);

  const setMode = useCallback(
    (next: EditMode) => {
      const draw = drawRef.current;
      const id = closedIdRef.current;
      if (!draw || id === null) return;
      modeRef.current = next;
      setModeState(next);
      setNote(null);
      setNotice(null);
      if (next === "move") {
        draw.setMode("select");
        draw.selectFeature(id);
        map?.dragPan.enable();
        return;
      }
      // Taking a zone out has no official parcel or satellite outline to tap.
      const usable =
        next === "remove" && TAP_TOOLS.includes(toolRef.current)
          ? "trace"
          : toolRef.current;
      toolRef.current = usable;
      setToolState(usable);
      draw.setMode(MODE[usable]);
      if (map) setPanning(map, usable);
      setCorners(0);
    },
    [map],
  );

  const undo = useCallback(() => {
    const draw = drawRef.current;
    const id = closedIdRef.current;
    if (!draw || id === null) return;
    const { history: rest, shape } = popped(historyRef.current);
    if (!shape) return;
    historyRef.current = rest;
    setHistory(rest);
    shapesRef.current = null;
    setFit(null);
    draw.setMode("select");
    try {
      draw.deselectFeature(id);
    } catch {
      // It was not selected.
    }
    draw.updateFeatureGeometry(id, shape);
    draw.selectFeature(id);
    lastRef.current = shape;
    setPolygon(shape);
    setHectares(area(shape) / 10_000);
    modeRef.current = "move";
    setModeState("move");
    setNote(null);
    map?.dragPan.enable();
  }, [map]);

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
      lastRef.current = applied ? shapes.fitted : shapes.drawn;
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
    closeEnough: zoom >= PARCELS_MIN_ZOOM,
    mode,
    setMode,
    undo,
    canUndo: history.length > 0,
    note,
  };
}
