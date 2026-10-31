import { describe, expect, it } from "vitest";

import type { Notifications } from "../api/client";
import { activePreset, applyPreset, kindOn } from "./presets";

const channels = (email: boolean, telegram = false, push = false) => ({
  email,
  telegram,
  push,
});
// What a new account has: mail for everything near, nothing for distant fires.
const defaults = (): Notifications => ({
  fire_high: channels(true, true, true),
  fire_medium: channels(true, true, true),
  fire_far: channels(false),
  lightning: channels(true, true, true),
  weather: channels(true, true, true),
  summary: channels(true),
});
const mailOnly = { email: true, telegram: false, push: false };
const everything = { email: true, telegram: true, push: true };

describe("notification presets", () => {
  it("turn kinds on in every channel that can be used, and the rest off", () => {
    const urgent = applyPreset(defaults(), "urgent", everything);
    expect(urgent.fire_high).toEqual(channels(true, true, true));
    expect(urgent.fire_medium).toEqual(channels(false));
    expect(urgent.weather).toEqual(channels(false));
    const all = applyPreset(defaults(), "all", everything);
    expect(all.fire_far).toEqual(channels(true, true, true));
  });

  it("leave a channel that cannot be used yet as it was, and the summary alone", () => {
    const current = defaults();
    current.fire_medium = channels(true, true, false);
    const next = applyPreset(current, "none", mailOnly);
    expect(next.fire_medium).toEqual(channels(false, true, false));
    expect(next.summary).toEqual(current.summary);
  });

  it("silence turns every danger off", () => {
    const next = applyPreset(defaults(), "none", everything);
    expect(
      ["fire_high", "fire_medium", "fire_far", "lightning", "weather"].map(
        (k) => kindOn(next[k as keyof Notifications], everything),
      ),
    ).toEqual([false, false, false, false, false]);
  });

  it("recognize which one the choices match, and none when they match no preset", () => {
    expect(activePreset(defaults(), everything)).toBe("important");
    expect(
      activePreset(applyPreset(defaults(), "urgent", everything), everything),
    ).toBe("urgent");
    expect(
      activePreset(applyPreset(defaults(), "all", mailOnly), mailOnly),
    ).toBe("all");
    expect(
      activePreset(applyPreset(defaults(), "none", everything), everything),
    ).toBe("none");
    const custom = defaults();
    custom.lightning = channels(false);
    expect(activePreset(custom, everything)).toBeNull();
  });
});
