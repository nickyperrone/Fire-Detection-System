import { describe, expect, it } from "vitest";

import type { FireAnswer, SprayAnswer } from "../api/client";
import { fireTone, sprayTone } from "./status";

const noFire: FireAnswer = {
  data_quality: "GOOD",
  last_read_at: null,
  severity: null,
  distance_m: null,
  direction: null,
  sensors: [],
  confidence: null,
  acquired_at: null,
  received_at: null,
  fire_event_id: null,
  other_fires: 0,
};

describe("fire tone", () => {
  it("is green only when the sources were read", () => {
    expect(fireTone(noFire)).toBe("ok");
    expect(fireTone({ ...noFire, data_quality: "PARTIAL" })).toBe("ok");
    expect(fireTone({ ...noFire, data_quality: "NO_DATA" })).toBe("unknown");
    expect(fireTone({ ...noFire, data_quality: "STALE" })).toBe("unknown");
  });

  it("follows severity", () => {
    expect(fireTone({ ...noFire, severity: "CRITICAL" })).toBe("critical");
    expect(fireTone({ ...noFire, severity: "VERY_HIGH" })).toBe("high");
    expect(fireTone({ ...noFire, severity: "WATCH" })).toBe("watch");
  });
});

describe("spray tone", () => {
  const spray: SprayAnswer = {
    data_quality: "GOOD",
    profile: "default",
    status: "CAUTION",
    valid_at: null,
    problems: [],
    drift_toward: null,
    next_favorable: null,
  };
  it("maps status and hides stale forecasts", () => {
    expect(sprayTone(spray)).toBe("watch");
    expect(sprayTone({ ...spray, status: "UNFAVORABLE" })).toBe("critical");
    expect(sprayTone({ ...spray, data_quality: "STALE" })).toBe("unknown");
  });
});
