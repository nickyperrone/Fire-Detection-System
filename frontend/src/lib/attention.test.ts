import { describe, expect, it } from "vitest";

import type { PortfolioEntry } from "../api/client";
import { allFine, attention } from "./status";

const calm: PortfolioEntry = {
  territory_id: 1,
  name: "Campo Larroque",
  kind: "FIELD",
  parent_id: null,
  hectares: 316,
  tags: [],
  alerts: true,
  visible: true,
  priority: "NORMAL",
  fire: {
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
  },
  spray: {
    data_quality: "GOOD",
    profile: "default",
    status: "FAVORABLE",
    valid_at: null,
    problems: [],
    drift_toward: null,
    next_favorable: null,
  },
  weather: {
    data_quality: "GOOD",
    valid_at: null,
    temperature_c: 18,
    relative_humidity_pct: 60,
    wind_speed_kmh: 7,
    wind_from: "NE",
    wind_gusts_kmh: 17,
    cloud_cover_pct: 0,
    rain_24h_mm: 0,
    rain_probability_pct: 0,
  },
  lightning: {
    data_quality: "GOOD",
    window_minutes: 60,
    flashes: 0,
    nearest_m: null,
    last_at: null,
  },
  forecast: { data_quality: "GOOD", issued_at: null, days: [] },
  anomaly: {
    data_quality: "GOOD",
    observed_on: null,
    patches: [],
    checked_at: null,
  },
};

const patch = {
  kind: "less_green",
  area_ha: 12,
  where: "NE",
  observed_on: "2026-10-04",
  lot: null,
};

describe("attention", () => {
  it("puts a fire before lightning, an unusual patch and spraying", () => {
    const fire: PortfolioEntry = {
      ...calm,
      fire: { ...calm.fire, severity: "WATCH" },
    };
    const lightning = { ...calm, lightning: { ...calm.lightning, flashes: 2 } };
    const unusual = { ...calm, anomaly: { ...calm.anomaly, patches: [patch] } };
    const noSpray: PortfolioEntry = {
      ...calm,
      spray: { ...calm.spray, status: "CAUTION" },
    };
    const ranks = [calm, noSpray, unusual, lightning, fire].map(attention);
    expect(ranks).toEqual([4, 3, 2, 1, 0]);
  });

  it("calls a field fine only when every answer is in and green", () => {
    expect(allFine(calm)).toBe(true);
    const unread: PortfolioEntry = {
      ...calm,
      fire: { ...calm.fire, data_quality: "NO_DATA" },
    };
    expect(allFine(unread)).toBe(false);
  });
});
