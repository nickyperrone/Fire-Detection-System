import type { WindLayer } from "../api/client";

/** Wind (east, north, km/h) at a point, interpolated between the four nearest grid points;
 * null outside the grid (docs/06-goes.md#wind-on-the-map). Rows run north to south. */
export function windAt(
  grid: Pick<WindLayer, "bbox" | "nx" | "ny" | "dx" | "u" | "v">,
  lon: number,
  lat: number,
): [number, number] | null {
  const [west, , , north] = grid.bbox;
  const x = (lon - west) / grid.dx;
  const y = (north - lat) / grid.dx;
  if (x < 0 || y < 0 || x > grid.nx - 1 || y > grid.ny - 1) return null;
  const x0 = Math.min(Math.floor(x), grid.nx - 2);
  const y0 = Math.min(Math.floor(y), grid.ny - 2);
  const fx = x - x0;
  const fy = y - y0;
  const at = (values: number[]) => {
    const i = y0 * grid.nx + x0;
    const top = values[i] * (1 - fx) + values[i + 1] * fx;
    const bottom =
      values[i + grid.nx] * (1 - fx) + values[i + grid.nx + 1] * fx;
    return top * (1 - fy) + bottom * fy;
  };
  return [at(grid.u), at(grid.v)];
}

// Slow wind is pale, a gale is orange: the same scale on every map and at every zoom.
const STOPS: [number, [number, number, number]][] = [
  [0, [186, 230, 253]],
  [15, [167, 243, 208]],
  [30, [253, 224, 71]],
  [50, [251, 146, 60]],
];

/** "r, g, b" for a wind speed in km/h. */
export function windColor(kmh: number): string {
  for (let i = STOPS.length - 1; i >= 0; i--) {
    const [from, a] = STOPS[i];
    if (kmh >= from) {
      const next = STOPS[i + 1];
      if (!next) return a.join(",");
      const t = (kmh - from) / (next[0] - from);
      return a.map((c, k) => Math.round(c + (next[1][k] - c) * t)).join(",");
    }
  }
  return STOPS[0][1].join(",");
}
