import { describe, expect, it } from "vitest";

import { dangerGrew } from "./danger";

const calm = { fire: 0, lightning: false };

describe("danger grew", () => {
  it("is not news the first time a field is seen", () => {
    expect(dangerGrew(undefined, { fire: 4, lightning: true })).toBe(false);
  });

  it("is news when a fire appears or comes closer", () => {
    expect(dangerGrew(calm, { fire: 1, lightning: false })).toBe(true);
    expect(
      dangerGrew({ fire: 2, lightning: false }, { fire: 3, lightning: false }),
    ).toBe(true);
  });

  it("is news when lightning starts, not while it lasts", () => {
    expect(dangerGrew(calm, { fire: 0, lightning: true })).toBe(true);
    expect(
      dangerGrew({ fire: 0, lightning: true }, { fire: 0, lightning: true }),
    ).toBe(false);
  });

  it("is not news when the danger stays or eases", () => {
    expect(
      dangerGrew({ fire: 3, lightning: false }, { fire: 3, lightning: false }),
    ).toBe(false);
    expect(
      dangerGrew({ fire: 3, lightning: true }, { fire: 1, lightning: false }),
    ).toBe(false);
  });
});
