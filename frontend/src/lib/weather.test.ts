import { describe, expect, it } from "vitest";

import type { Weather } from "../api/client";
import { MESSAGES } from "../i18n/messages";
import { weatherLine } from "./weather";

const weather: Weather = {
  data_quality: "GOOD",
  valid_at: "2026-10-04T15:00:00Z",
  temperature_c: 21.6,
  relative_humidity_pct: 58,
  wind_speed_kmh: 12.2,
  wind_from: "SW",
  wind_gusts_kmh: 23.4,
  cloud_cover_pct: 40,
  rain_24h_mm: 4.25,
  rain_probability_pct: 70,
};

describe("weather line", () => {
  it("reads in Spanish with the wind's origin", () => {
    expect(weatherLine(MESSAGES.es, weather)).toBe(
      "22° · viento del SO 12 km/h · ráfagas 23 · 4,3 mm en 24 h",
    );
  });

  it("leaves out rain when none is expected", () => {
    expect(weatherLine(MESSAGES.en, { ...weather, rain_24h_mm: 0 })).toBe(
      "22° · wind from SW 12 km/h · gusts 23",
    );
  });

  it("is empty without data", () => {
    expect(
      weatherLine(MESSAGES.en, { ...weather, data_quality: "NO_DATA" }),
    ).toBeNull();
  });
});
