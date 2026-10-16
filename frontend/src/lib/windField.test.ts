import { describe, expect, it } from "vitest";

import { windAt, windColor } from "./windField";

// Two columns, two rows: west column blows east at 10, east column at 20; north 0, south 10.
const grid = {
  bbox: [-60, -34, -58.5, -32.5],
  nx: 2,
  ny: 2,
  dx: 1.5,
  u: [10, 20, 10, 20],
  v: [0, 0, 10, 10],
};

describe("wind field", () => {
  it("interpolates between grid points and leaves the outside out", () => {
    expect(windAt(grid, -60, -32.5)).toEqual([10, 0]);
    expect(windAt(grid, -59.25, -33.25)).toEqual([15, 5]);
    expect(windAt(grid, -58.5, -34)).toEqual([20, 10]);
    expect(windAt(grid, -50, -33)).toBeNull();
  });

  it("colors by speed from pale to orange", () => {
    expect(windColor(0)).toBe("186,230,253");
    expect(windColor(80)).toBe("251,146,60");
    expect(windColor(15)).toBe("167,243,208");
  });
});
