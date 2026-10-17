import { describe, expect, it } from "vitest";

import { addPiece, clipTo, largest, removePiece, type Shape } from "./shapeOps";
import area from "@turf/area";

// Squares of 0.01° (about 1 km) near Larroque, at the given west and south corner.
function square(west: number, south: number, side = 0.01): Shape {
  const east = west + side;
  const north = south + side;
  return {
    type: "Polygon",
    coordinates: [
      [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
      ],
    ],
  };
}
const ha = (s: Shape | null) => (s ? area(s) / 10_000 : 0);
const base = square(-59.05, -32.98);

describe("adding a zone", () => {
  it("joins an overlapping piece to the shape", () => {
    const result = addPiece(base, square(-59.045, -32.98));
    expect(result.note).toBeNull();
    expect(ha(result.shape)).toBeGreaterThan(ha(base));
    expect(ha(result.shape)).toBeLessThan(ha(base) * 1.6);
  });

  it("keeps the biggest piece when the zone is apart, and says so", () => {
    const result = addPiece(base, square(-59.0, -32.98, 0.004));
    expect(result.note).toBe("kept_largest");
    expect(ha(result.shape)).toBeCloseTo(ha(base), 0);
  });
});

describe("removing a zone", () => {
  it("takes a corner out of the shape", () => {
    const result = removePiece(base, square(-59.0455, -32.9745, 0.01));
    expect(result.note).toBeNull();
    expect(ha(result.shape)).toBeLessThan(ha(base));
    expect(ha(result.shape)).toBeGreaterThan(ha(base) / 2);
  });

  it("says when the zone does not touch the shape", () => {
    expect(removePiece(base, square(-59.0, -32.98)).note).toBe("piece_outside");
  });

  it("will not take the whole field away", () => {
    const result = removePiece(base, square(-59.051, -32.981, 0.012));
    expect(result).toEqual({ shape: null, note: "removed_all" });
  });

  it("keeps the bigger half when the zone cuts the field in two", () => {
    const band = {
      type: "Polygon",
      coordinates: [
        [
          [-59.0475, -32.99],
          [-59.0465, -32.99],
          [-59.0465, -32.97],
          [-59.0475, -32.97],
          [-59.0475, -32.99],
        ],
      ],
    } as Shape;
    const result = removePiece(base, band);
    expect(result.note).toBe("kept_largest");
    expect(ha(result.shape)).toBeGreaterThan(ha(base) * 0.6);
  });
});

describe("a lot inside its field", () => {
  const parent = square(-59.05, -32.98, 0.02);

  it("is left alone when it already fits", () => {
    const lot = square(-59.045, -32.975, 0.005);
    const result = clipTo(lot, parent);
    expect(result.note).toBeNull();
    expect(ha(result.shape)).toBeCloseTo(ha(lot), 1);
  });

  it("is cut to the field's edge, and says so", () => {
    const result = clipTo(square(-59.055, -32.975, 0.01), parent);
    expect(result.note).toBe("clipped");
    expect(ha(result.shape)).toBeLessThan(ha(square(-59.055, -32.975, 0.01)));
  });

  it("has nothing to keep outside the field", () => {
    expect(clipTo(square(-59.2, -32.5), parent)).toEqual({
      shape: null,
      note: "outside_parent",
    });
  });
});

describe("coordinates", () => {
  it("come out with no more than 8 decimals, which the drawing layer requires", () => {
    const pieces = [
      addPiece(base, square(-59.0451234567891, -32.98)).shape,
      removePiece(base, square(-59.0455123456789, -32.9745)).shape,
    ];
    for (const shape of pieces) {
      for (const [x, y] of shape!.coordinates[0]) {
        for (const n of [x, y]) {
          expect(String(n).split(".")[1]?.length ?? 0).toBeLessThanOrEqual(8);
        }
      }
    }
  });
});

describe("largest piece", () => {
  it("drops holes and smaller parts", () => {
    const big = square(-59.05, -32.98).coordinates[0];
    const small = square(-59.0, -32.98, 0.001).coordinates[0];
    const found = largest({
      type: "MultiPolygon",
      coordinates: [[small], [big, small]],
    });
    expect(found.coordinates).toEqual([big]);
  });
});
