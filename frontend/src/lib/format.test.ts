import { describe, expect, it } from "vitest";

import { formatAge, formatHectares, formatKm, localTime } from "./format";

describe("formatAge", () => {
  const now = new Date("2026-09-30T12:00:00Z");
  it.each([
    ["2026-09-30T11:59:40Z", "just now"],
    ["2026-09-30T11:55:00Z", "5 min ago"],
    ["2026-09-30T09:00:00Z", "3 h ago"],
    ["2026-09-27T12:00:00Z", "3 d ago"],
  ])("%s is %s", (iso, expected) => expect(formatAge(iso, now)).toBe(expected));

  it("says unknown without a timestamp", () => expect(formatAge(null, now)).toBe("unknown"));
});

describe("formatKm", () => {
  it("uses meters below 1 km and says inside at 0", () => {
    expect(formatKm(0)).toBe("inside");
    expect(formatKm(640.4)).toBe("640 m");
    expect(formatKm(3720)).toBe("3.7 km");
  });
});

describe("local time", () => {
  it("shows Argentina time (UTC-3)", () => expect(localTime("2026-09-30T12:00:00Z")).toBe("09:00"));
  it("formats hectares", () => expect(formatHectares(1240.4)).toBe("1,240 ha"));
});
