import { describe, expect, it } from "vitest";

import { pixelAt, skyOf } from "./weatherHere";

const BBOX: [number, number, number, number] = [-76, -56.5, -50, -20.5];

describe("weather here", () => {
  it("finds the corners and leaves outside points out", () => {
    expect(pixelAt(BBOX, 100, 100, -76, -20.5)).toEqual([0, 0]);
    expect(pixelAt(BBOX, 100, 100, -50, -56.5)).toEqual([99, 99]);
    expect(pixelAt(BBOX, 100, 100, -40, -30)).toBeNull();
  });

  it("puts a middle latitude below the middle row, as Mercator stretches the south", () => {
    const [, y] = pixelAt(BBOX, 100, 100, -63, -38.5)!;
    expect(y).toBeLessThan(50);
  });

  it("reads rain over clouds, and a faint edge as clear", () => {
    const px = (...values: number[]) => new Uint8ClampedArray(values);
    expect(skyOf(px(240, 244, 248, 5))).toBe("clear");
    expect(skyOf(px(240, 244, 248, 60))).toBe("clouds");
    expect(skyOf(px(240, 244, 248, 60, 37, 99, 235, 217))).toBe("moderate");
  });
});
