import { describe, expect, it } from "vitest";

import { MESSAGES } from "./messages";
import { formatAge, formatDistance, formatHectares, localTime, ruleSentence } from "./text";

const { en, es } = MESSAGES;

describe("formatAge", () => {
  const now = new Date("2026-09-30T12:00:00Z");
  it.each([
    ["2026-09-30T11:59:40Z", "just now", "recién"],
    ["2026-09-30T11:55:00Z", "5 min ago", "hace 5 min"],
    ["2026-09-30T09:00:00Z", "3 h ago", "hace 3 h"],
    ["2026-09-27T12:00:00Z", "3 d ago", "hace 3 d"],
  ])("%s", (iso, english, spanish) => {
    expect(formatAge(en, iso, now)).toBe(english);
    expect(formatAge(es, iso, now)).toBe(spanish);
  });
});

describe("numbers and places", () => {
  it("uses each language's number format", () => {
    expect(formatHectares(en, 1240.4)).toBe("1,240 ha");
    expect(formatHectares(es, 1240.4)).toBe("1.240 ha");
    expect(formatDistance(es, 3720)).toBe("3,7 km");
    expect(formatDistance(en, 0)).toBe("inside");
  });

  it("shows Argentina time (UTC-3)", () => {
    expect(localTime(en, "2026-09-30T12:00:00Z")).toBe("09:00");
  });
});

describe("ruleSentence", () => {
  const rule = {
    rule: "gusts",
    status: "FAIL" as const,
    value: 23.4,
    unit: "km/h",
    limit: 20,
    estimated: false,
    window_h: null,
  };
  it("writes the rule in each language from its numbers", () => {
    expect(ruleSentence(en, rule)).toBe("Gusts 23 km/h, over 20 km/h");
    expect(ruleSentence(es, rule)).toBe("Ráfagas 23 km/h, más que 20 km/h");
  });
  it("explains calm wind and rain chance", () => {
    expect(ruleSentence(es, { ...rule, rule: "wind", status: "CAUTION", value: 2, limit: 3 })).toBe(
      "Viento de solo 2 km/h: la deriva queda suspendida",
    );
    expect(
      ruleSentence(en, { ...rule, rule: "rain", status: "CAUTION", value: 60, unit: "%", limit: 50, window_h: 2 }),
    ).toBe("60 % chance of rain in the next 2 h");
  });
  it("names the inversion as an estimate", () => {
    expect(ruleSentence(es, { ...rule, rule: "inversion", status: "CAUTION", value: null, unit: "", limit: null })).toMatch(
      /estimada/,
    );
  });
});
