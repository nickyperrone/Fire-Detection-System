"use client";

import area from "@turf/area";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { Marker } from "maplibre-gl";
import { useEffect } from "react";

type Point = [number, number];

// An example: a real parcel from Entre Ríos' cadastre near Larroque (public data, 541 ha) and a
// fire 3.7 km to its northeast. The map plays what Field Watch does for someone who has not signed
// in yet: an outline drawn by hand fits to the property lines (docs/04-frontend.md#first-visit).
const FIELD: Point[] = [
  [-59.05603, -32.96211],
  [-59.04573, -32.96386],
  [-59.03756, -32.96572],
  [-59.03188, -32.96715],
  [-59.02125, -32.9677],
  [-59.02504, -32.98412],
  [-59.05899, -32.97554],
  [-59.05603, -32.96211],
];
const FIELD_CORNER: Point = [-59.02125, -32.9677];
const FIRE: Point = [-58.99324, -32.9442];
const WIDE = { center: [-59.6, -33.4] as Point, zoom: 6.2 };
const SCENE_BOUNDS: [Point, Point] = [
  [-59.059, -32.9842],
  [-58.9932, -32.9442],
];
const LABEL_AT: Point = [-59.04, -32.9815];
const HECTARES = area({ type: "Polygon", coordinates: [FIELD] }) / 10_000;
// The outline traced by hand first, then fitted to the field's limits: the same number of points,
// so one can turn into the other.
const SAMPLES = 64;

const FIELD_BOUNDS: [Point, Point] = [
  [-59.05899, -32.98412],
  [-59.02125, -32.96211],
];

/** A box framed in the part of the map the panel leaves free: the field alone, close enough for
 * the property lines (zoom 13 and up), or the field and the fire. */
function sceneCamera(map: MapLibreMap, bounds: [Point, Point] = SCENE_BOUNDS) {
  const mobile = window.innerWidth < 768;
  const padding = mobile
    ? { top: 110, bottom: window.innerHeight * 0.55, left: 40, right: 60 }
    : { top: 90, bottom: 90, left: 470, right: 110 };
  const camera = map.cameraForBounds(bounds, { padding });
  return {
    center: camera?.center ?? ([-59.019, -33.002] as [number, number]),
    zoom: camera?.zoom ?? 13,
  };
}

const SOURCE = "intro";
const LAYERS = [
  "intro-fill",
  "intro-outline",
  "intro-sketch",
  "intro-distance",
];

type Scene = {
  sketch: Point[];
  outline: Point[];
  distance: Point[];
};
const EMPTY: Scene = { sketch: [], outline: [], distance: [] };

function data({ sketch, outline, distance }: Scene): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  if (sketch.length > 1)
    features.push({
      type: "Feature",
      properties: { kind: "sketch" },
      geometry: { type: "LineString", coordinates: sketch },
    });
  if (outline.length > 1)
    features.push({
      type: "Feature",
      properties: { kind: "outline" },
      geometry: { type: "LineString", coordinates: outline },
    });
  if (outline.length > 1)
    features.push({
      type: "Feature",
      properties: { kind: "field" },
      geometry: { type: "Polygon", coordinates: [FIELD] },
    });
  if (distance.length > 1)
    features.push({
      type: "Feature",
      properties: { kind: "distance" },
      geometry: { type: "LineString", coordinates: distance },
    });
  return { type: "FeatureCollection", features };
}

function addLayers(map: MapLibreMap, scene: Scene) {
  if (map.getSource(SOURCE)) {
    (map.getSource(SOURCE) as GeoJSONSource).setData(data(scene));
    return;
  }
  map.addSource(SOURCE, { type: "geojson", data: data(scene) });
  map.addLayer({
    id: "intro-fill",
    type: "fill",
    source: SOURCE,
    filter: ["==", ["get", "kind"], "field"],
    paint: {
      "fill-color": "#4ade80",
      "fill-opacity": 0.22,
      "fill-opacity-transition": { duration: 800 },
    },
  });
  map.addLayer({
    id: "intro-outline",
    type: "line",
    source: SOURCE,
    filter: ["==", ["get", "kind"], "outline"],
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": "#4ade80", "line-width": 3.5, "line-blur": 0.4 },
  });
  map.addLayer({
    id: "intro-sketch",
    type: "line",
    source: SOURCE,
    filter: ["==", ["get", "kind"], "sketch"],
    layout: { "line-join": "round", "line-cap": "round" },
    paint: {
      "line-color": "#ffffff",
      "line-width": 2.5,
      "line-dasharray": [1.5, 1.5],
    },
  });
  map.addLayer({
    id: "intro-distance",
    type: "line",
    source: SOURCE,
    filter: ["==", ["get", "kind"], "distance"],
    layout: { "line-cap": "round" },
    paint: {
      "line-color": "#ffffff",
      "line-width": 2.5,
      "line-dasharray": [2, 2],
    },
  });
}

function removeLayers(map: MapLibreMap) {
  for (const id of LAYERS) if (map.getLayer(id)) map.removeLayer(id);
  if (map.getSource(SOURCE)) map.removeSource(SOURCE);
}

// The map moves a marker with `transform`, so the animated element sits inside it.
function marker(className: string, text = ""): HTMLElement {
  const outer = document.createElement("div");
  const inner = document.createElement("div");
  inner.className = className;
  inner.textContent = text;
  outer.append(inner);
  return outer;
}

const label = (text: string, className: string) => marker(className, text);
const fireDot = () => marker("intro-fire");

/** Points along a path, `t` from 0 to 1 of its length. */
function along(path: [number, number][], t: number): [number, number][] {
  const lengths = path
    .slice(1)
    .map((p, i) => Math.hypot(p[0] - path[i][0], p[1] - path[i][1]));
  const total = lengths.reduce((a, b) => a + b, 0);
  let left = total * t;
  const out: [number, number][] = [path[0]];
  for (let i = 0; i < lengths.length; i++) {
    if (left >= lengths[i]) {
      out.push(path[i + 1]);
      left -= lengths[i];
      continue;
    }
    const f = left / lengths[i];
    out.push([
      path[i][0] + (path[i + 1][0] - path[i][0]) * f,
      path[i][1] + (path[i + 1][1] - path[i][1]) * f,
    ]);
    break;
  }
  return out;
}

const ease = (t: number) => 1 - Math.pow(1 - t, 3);

/** `n` + 1 points evenly along a closed path, the last one on the first. */
function resample(path: Point[], n: number): Point[] {
  return Array.from({ length: n + 1 }, (_, i) => {
    const part = along(path, i / n);
    return part[part.length - 1];
  });
}

const FITTED = resample(FIELD, SAMPLES);
// A hand's line: a little off the limits, the same each time.
const SKETCHED: Point[] = FITTED.map(([lon, lat], i) => {
  const j = i % SAMPLES;
  const wobble = Math.sin(j * 1.7) * 0.0009 + Math.sin(j * 0.45 + 1) * 0.0011;
  return [lon + wobble, lat - wobble * 0.8];
});

function blend(from: Point[], to: Point[], t: number): Point[] {
  return from.map(([x, y], i) => [
    x + (to[i][0] - x) * t,
    y + (to[i][1] - y) * t,
  ]);
}

/**
 * The first visit's film: a flight to Larroque, an example field traced, a fire with its distance,
 * a slow drift, then out and again. It stops for good at the first touch of the map, and stands
 * still on the finished scene for people who ask their system for less motion.
 */
export function useIntroTour(
  map: MapLibreMap | null,
  active: boolean,
  labels: { field: string; distance: string; intl: string },
) {
  const { distance: distanceLabel } = labels;
  const hectares = new Intl.NumberFormat(labels.intl, {
    maximumFractionDigits: 0,
  }).format(HECTARES);
  const fieldLabel = `${labels.field} · ${hectares} ha`;
  useEffect(() => {
    if (!map || !active) return;
    let stopped = false;
    const timers: number[] = [];
    const frames: number[] = [];
    const markers: Marker[] = [];
    let scene: Scene = EMPTY;

    const wait = (ms: number) =>
      new Promise<void>((resolve) =>
        timers.push(window.setTimeout(resolve, ms)),
      );
    const moved = () =>
      new Promise<void>((resolve) => {
        if (!map.isMoving()) return resolve();
        map.once("moveend", () => resolve());
      });
    const animate = (ms: number, step: (t: number) => void) =>
      new Promise<void>((resolve) => {
        const start = performance.now();
        const tick = (now: number) => {
          if (stopped) return resolve();
          const t = Math.min(1, (now - start) / ms);
          step(ease(t));
          if (t < 1) frames.push(requestAnimationFrame(tick));
          else resolve();
        };
        frames.push(requestAnimationFrame(tick));
      });
    const draw = (next: Partial<Scene>) => {
      scene = { ...scene, ...next };
      if (map.getStyle()) addLayers(map, scene);
    };
    const clear = () => {
      markers.splice(0).forEach((m) => m.remove());
      scene = EMPTY;
      if (map.getStyle()) removeLayers(map);
    };
    // A new basemap drops our layers; they come back with the scene as it was.
    const restore = () => !stopped && addLayers(map, scene);
    map.on("style.load", restore);

    const finished = () => {
      draw({ outline: FITTED, distance: [FIELD_CORNER, FIRE] });
      markers.push(
        new Marker({ element: label(fieldLabel, "intro-label") })
          .setLngLat(LABEL_AT)
          .setOffset([0, 18])
          .addTo(map),
        new Marker({ element: fireDot() }).setLngLat(FIRE).addTo(map),
        new Marker({
          element: label(distanceLabel, "intro-label intro-label-white"),
        })
          .setLngLat([
            (FIELD_CORNER[0] + FIRE[0]) / 2,
            (FIELD_CORNER[1] + FIRE[1]) / 2,
          ])
          .addTo(map),
      );
    };

    const play = async () => {
      if (!map.loaded()) await new Promise((r) => map.once("load", r));
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        map.jumpTo(sceneCamera(map));
        finished();
        return;
      }
      while (!stopped) {
        clear();
        map.jumpTo(WIDE);
        await wait(900);
        if (stopped) return;
        // Close on the field to draw it.
        const close = sceneCamera(map, FIELD_BOUNDS);
        map.flyTo({ ...close, duration: 6500, curve: 1.5 });
        await moved();
        if (stopped) return;
        // A dotted line traced by hand; it fits to the property line and turns green; then its
        // hectares.
        await animate(2800, (t) => draw({ sketch: along(SKETCHED, t) }));
        if (stopped) return;
        await wait(300);
        await animate(900, (t) => draw({ sketch: blend(SKETCHED, FITTED, t) }));
        if (stopped) return;
        draw({ sketch: [], outline: FITTED });
        await wait(400);
        markers.push(
          new Marker({ element: label(fieldLabel, "intro-label") })
            .setLngLat(LABEL_AT)
            .setOffset([0, 18])
            .addTo(map),
        );
        await wait(900);
        if (stopped) return;
        // Then back a little: the fire and how far it is.
        const camera = sceneCamera(map);
        map.easeTo({ ...camera, duration: 1800 });
        await moved();
        if (stopped) return;
        markers.push(
          new Marker({ element: fireDot() }).setLngLat(FIRE).addTo(map),
        );
        await wait(700);
        await animate(1600, (t) =>
          draw({ distance: along([FIELD_CORNER, FIRE], t) }),
        );
        if (stopped) return;
        markers.push(
          new Marker({
            element: label(distanceLabel, "intro-label intro-label-white"),
          })
            .setLngLat([
              (FIELD_CORNER[0] + FIRE[0]) / 2,
              (FIELD_CORNER[1] + FIRE[1]) / 2,
            ])
            .addTo(map),
        );
        // A slow push in, like a camera holding on the scene.
        map.easeTo({
          zoom: camera.zoom + 0.3,
          duration: 9000,
          easing: (t) => t,
        });
        await moved();
        await wait(1200);
        if (stopped) return;
        clear();
        map.easeTo({ ...WIDE, duration: 4500 });
        await moved();
        await wait(600);
      }
    };

    // The first touch hands the map over: the film stops where it is.
    const stop = () => {
      if (stopped) return;
      stopped = true;
      map.stop();
      map.off("style.load", restore);
    };
    const events = ["mousedown", "touchstart", "wheel"] as const;
    for (const event of events) map.on(event, stop);
    void play();

    return () => {
      stop();
      for (const event of events) map.off(event, stop);
      timers.forEach(window.clearTimeout);
      frames.forEach(cancelAnimationFrame);
      clear();
    };
  }, [map, active, fieldLabel, distanceLabel]);
}
