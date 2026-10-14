"use client";

import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { Marker } from "maplibre-gl";
import { useEffect } from "react";

// An example field near Larroque and a fire 3.7 km to its northeast: the map plays what Field
// Watch does for someone who has not signed in yet (docs/04-frontend.md#first-visit).
const FIELD: [number, number][] = [
  [-59.042, -33.0105],
  [-59.0285, -33.009],
  [-59.027, -33.0185],
  [-59.0335, -33.0215],
  [-59.043, -33.02],
  [-59.042, -33.0105],
];
const FIELD_CORNER: [number, number] = [-59.0285, -33.009];
const FIRE: [number, number] = [-59.0004, -32.9854];
const WIDE = { center: [-59.6, -33.4] as [number, number], zoom: 6.2 };
const SCENE_BOUNDS: [[number, number], [number, number]] = [
  [-59.043, -33.0215],
  [-59.0004, -32.9854],
];

/** The field and the fire framed in the part of the map the panel leaves free. */
function sceneCamera(map: MapLibreMap) {
  const mobile = window.innerWidth < 768;
  const padding = mobile
    ? { top: 110, bottom: window.innerHeight * 0.55, left: 40, right: 60 }
    : { top: 90, bottom: 90, left: 470, right: 110 };
  const camera = map.cameraForBounds(SCENE_BOUNDS, { padding });
  return {
    center: camera?.center ?? ([-59.019, -33.002] as [number, number]),
    zoom: camera?.zoom ?? 13,
  };
}

const SOURCE = "intro";
const LAYERS = ["intro-fill", "intro-outline", "intro-distance"];

type Scene = { outline: [number, number][]; distance: [number, number][] };

function data({ outline, distance }: Scene): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  if (outline.length > 1)
    features.push({
      type: "Feature",
      properties: { kind: "outline" },
      geometry: { type: "LineString", coordinates: outline },
    });
  if (outline.length === FIELD.length)
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

/**
 * The first visit's film: a flight to Larroque, an example field traced, a fire with its distance,
 * a slow drift, then out and again. It stops for good at the first touch of the map, and stands
 * still on the finished scene for people who ask their system for less motion.
 */
export function useIntroTour(
  map: MapLibreMap | null,
  active: boolean,
  labels: { field: string; distance: string },
) {
  const { field: fieldLabel, distance: distanceLabel } = labels;
  useEffect(() => {
    if (!map || !active) return;
    let stopped = false;
    const timers: number[] = [];
    const frames: number[] = [];
    const markers: Marker[] = [];
    let scene: Scene = { outline: [], distance: [] };

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
      scene = { outline: [], distance: [] };
      if (map.getStyle()) removeLayers(map);
    };
    // A new basemap drops our layers; they come back with the scene as it was.
    const restore = () => !stopped && addLayers(map, scene);
    map.on("style.load", restore);

    const finished = () => {
      draw({ outline: FIELD, distance: [FIELD_CORNER, FIRE] });
      markers.push(
        new Marker({ element: label(fieldLabel, "intro-label") })
          .setLngLat([-59.035, -33.0215])
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
        const camera = sceneCamera(map);
        map.flyTo({ ...camera, duration: 6500, curve: 1.5 });
        await moved();
        if (stopped) return;
        await animate(2600, (t) => draw({ outline: along(FIELD, t) }));
        if (stopped) return;
        draw({ outline: FIELD });
        markers.push(
          new Marker({ element: label(fieldLabel, "intro-label") })
            .setLngLat([-59.035, -33.0215])
            .setOffset([0, 18])
            .addTo(map),
        );
        await wait(900);
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
