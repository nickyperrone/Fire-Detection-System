import area from "@turf/area";
import { describe, expect, it } from "vitest";

import { simplifyRing } from "./geometry";

// A 1 km x 1 km square near Larroque traced with a point every ~10 m.
function tracedSquare(): number[][] {
  const [lon, lat, side] = [-59.05, -32.97, 0.0107];
  const corners = [
    [lon, lat],
    [lon + side, lat],
    [lon + side, lat + side * 0.9],
    [lon, lat + side * 0.9],
  ];
  const ring: number[][] = [];
  for (let c = 0; c < 4; c++) {
    const [a, b] = [corners[c], corners[(c + 1) % 4]];
    for (let i = 0; i < 100; i++) ring.push([a[0] + ((b[0] - a[0]) * i) / 100, a[1] + ((b[1] - a[1]) * i) / 100]);
  }
  ring.push(ring[0]);
  return ring;
}

describe("simplifyRing", () => {
  it("keeps only the corners of a traced square and its area", () => {
    const ring = tracedSquare();
    const simplified = simplifyRing(ring, 3);
    expect(simplified).toHaveLength(5);
    expect(simplified[0]).toEqual(simplified[simplified.length - 1]);
    const before = area({ type: "Polygon", coordinates: [ring] });
    const after = area({ type: "Polygon", coordinates: [simplified] });
    expect(after).toBeCloseTo(before, -2);
  });

  it("keeps a bend larger than the tolerance", () => {
    const ring = tracedSquare();
    ring[150] = [ring[150][0] + 0.0005, ring[150][1]]; // ~45 m bump on the east side
    expect(simplifyRing(ring, 3).length).toBeGreaterThan(5);
  });
});
