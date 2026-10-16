import { describe, expect, it } from "vitest";

import type { RiskEvent } from "../api/client";
import { MESSAGES } from "../i18n/messages";
import { span, windPush } from "./wind";

const es = MESSAGES.es;

describe("wind toward the field", () => {
  it("rounds the time of arrival more the further off it is", () => {
    expect(span(es, 0.4)).toBe("~25 min");
    expect(span(es, 2.4)).toBe("~2,4 h");
    expect(span(es, 5.2)).toBe("~5 h");
  });

  it("says nothing unless the wind blows from the fire", () => {
    const risk = (factors: object) => ({ factors }) as RiskEvent;
    expect(windPush(es, risk({ wind_toward: false, wind_kmh: 20 }))).toBeNull();
    const pushed = windPush(
      es,
      risk({ wind_toward: true, wind_kmh: 22, arrival_h: 2.4 }),
    );
    expect(pushed?.toward).toContain("22 km/h");
    expect(pushed?.arrival).toContain("~2,4 h");
  });
});
