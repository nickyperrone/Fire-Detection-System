import { describe, expect, it } from "vitest";

import type { Snapshot } from "../api/client";
import { monthStarts, newestClear } from "./photos";

const photo = (date: string, cloud_share: number): Snapshot => ({
  date,
  cloud_share,
  ndvi_mean: 0.5,
});

describe("the first photo shown", () => {
  it("is the newest clear one, not a newer cloudy one", () => {
    const photos = [photo("2026-09-16", 0), photo("2026-10-04", 0.44)];
    expect(newestClear(photos)).toBe(0);
  });

  it("is the newest when every photo has clouds", () => {
    const photos = [photo("2026-09-16", 0.3), photo("2026-10-04", 0.44)];
    expect(newestClear(photos)).toBe(1);
  });
});

describe("month marks on the greenness chart", () => {
  it("are the first days of the months inside the range, across a new year", () => {
    expect(monthStarts("2026-11-12", "2027-02-03")).toEqual([
      "2026-12-01",
      "2027-01-01",
      "2027-02-01",
    ]);
  });

  it("are none within a single month", () => {
    expect(monthStarts("2026-04-12", "2026-04-30")).toEqual([]);
  });
});
