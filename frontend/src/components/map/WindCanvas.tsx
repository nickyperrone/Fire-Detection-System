"use client";

import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useRef } from "react";

import type { WindLayer } from "@/api/client";
import { windAt, windColor } from "@/lib/windField";

// Pixels a particle moves per frame per km/h of wind, so the flow reads the same at every zoom:
// it is drawn on the screen, not stretched with the map.
const PX_PER_KMH = 0.05;
const CELL = 18; // pixels between the screen points the wind is sampled at
const FADE = 0.07; // how much of the trail is erased each frame
const MAX_AGE = 90;
const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

type Particle = { x: number; y: number; age: number };

/** Particles carried by the wind over the map (docs/06-goes.md#wind-on-the-map). The grid is
 * sampled on a coarse screen lattice each time the map stops, and the particles read that. While
 * the map moves the layer hides, so it never lags behind the ground. */
export function WindCanvas({
  map,
  grid,
}: {
  map: MapLibreMap | null;
  grid: WindLayer | null;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = canvas.current;
    if (!map || !grid || !el) return;
    const context = el.getContext("2d");
    if (!context) return;
    const still = window.matchMedia(REDUCED_MOTION).matches;
    let frame = 0;
    let particles: Particle[] = [];
    let field: {
      u: Float32Array;
      v: Float32Array;
      cols: number;
      rows: number;
    } | null = null;
    let width = 0;
    let height = 0;

    const clear = () => context.clearRect(0, 0, el.width, el.height);

    const build = () => {
      const box = map.getContainer().getBoundingClientRect();
      width = box.width;
      height = box.height;
      const dpr = window.devicePixelRatio || 1;
      el.width = Math.round(width * dpr);
      el.height = Math.round(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      const cols = Math.ceil(width / CELL) + 1;
      const rows = Math.ceil(height / CELL) + 1;
      const u = new Float32Array(cols * rows);
      const v = new Float32Array(cols * rows);
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const { lng, lat } = map.unproject([c * CELL, r * CELL]);
          const wind = windAt(grid, lng, lat);
          // North is up on screen, so the north component flips.
          u[r * cols + c] = wind ? wind[0] : NaN;
          v[r * cols + c] = wind ? -wind[1] : NaN;
        }
      }
      field = { u, v, cols, rows };
      const count = Math.min(
        2600,
        Math.max(500, Math.round((width * height) / 650)),
      );
      particles = Array.from({ length: count }, () =>
        seed(Math.random() * MAX_AGE),
      );
    };

    const seed = (age = 0): Particle => ({
      x: Math.random() * width,
      y: Math.random() * height,
      age,
    });

    const sample = (x: number, y: number): [number, number] | null => {
      if (!field) return null;
      const fx = x / CELL;
      const fy = y / CELL;
      const c = Math.min(Math.floor(fx), field.cols - 2);
      const r = Math.min(Math.floor(fy), field.rows - 2);
      if (c < 0 || r < 0) return null;
      const tx = fx - c;
      const ty = fy - r;
      const at = (a: Float32Array) => {
        const i = r * field!.cols + c;
        const top = a[i] * (1 - tx) + a[i + 1] * tx;
        const bottom =
          a[i + field!.cols] * (1 - tx) + a[i + field!.cols + 1] * tx;
        return top * (1 - ty) + bottom * ty;
      };
      const u = at(field.u);
      const v = at(field.v);
      return Number.isNaN(u) || Number.isNaN(v) ? null : [u, v];
    };

    const step = () => {
      // Erase a little of everything drawn so far: the trail.
      context.globalCompositeOperation = "destination-out";
      context.fillStyle = `rgba(0,0,0,${FADE})`;
      context.fillRect(0, 0, width, height);
      context.globalCompositeOperation = "source-over";
      context.lineWidth = 1.4;
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        const wind = sample(p.x, p.y);
        if (!wind || p.age > MAX_AGE) {
          particles[i] = seed();
          continue;
        }
        const kmh = Math.hypot(wind[0], wind[1]);
        const nx = p.x + wind[0] * PX_PER_KMH;
        const ny = p.y + wind[1] * PX_PER_KMH;
        context.strokeStyle = `rgba(${windColor(kmh)},0.85)`;
        context.beginPath();
        context.moveTo(p.x, p.y);
        context.lineTo(nx, ny);
        context.stroke();
        p.x = nx;
        p.y = ny;
        p.age += 1;
      }
      frame = requestAnimationFrame(step);
    };

    const start = () => {
      cancelAnimationFrame(frame);
      build();
      el.style.opacity = "1";
      if (still) {
        // A still picture of the flow for people who ask for less motion.
        for (let i = 0; i < 40; i++) step();
        cancelAnimationFrame(frame);
      } else {
        frame = requestAnimationFrame(step);
      }
    };
    const stop = () => {
      cancelAnimationFrame(frame);
      el.style.opacity = "0";
    };

    map.on("movestart", stop);
    map.on("moveend", start);
    map.on("resize", start);
    start();
    return () => {
      map.off("movestart", stop);
      map.off("moveend", start);
      map.off("resize", start);
      cancelAnimationFrame(frame);
      clear();
    };
  }, [map, grid]);

  return (
    <canvas
      ref={canvas}
      aria-hidden
      className="pointer-events-none absolute inset-0 size-full transition-opacity duration-300"
    />
  );
}
