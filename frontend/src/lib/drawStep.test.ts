import { describe, expect, it } from "vitest";

import {
  ALL_TOOLS,
  popped,
  pushed,
  stepOf,
  toolsFor,
  type StepInput,
} from "./drawStep";
import type { Shape } from "./shapeOps";

const base: StepInput = {
  hasShape: false,
  editingSaved: false,
  mode: "move",
  searching: false,
  closeEnough: true,
  hasNotice: false,
};
const step = (changes: Partial<StepInput>) => stepOf({ ...base, ...changes });

describe("step 1: marking the field", () => {
  it("offers every way to mark it, and the search, and nothing to adjust yet", () => {
    const s = step({});
    expect(s.phase).toBe("choose");
    expect(s.tools).toEqual(ALL_TOOLS);
    expect(s.search).toBe(true);
    expect(s.editBar).toBe(false);
    expect(s.save).toBe(false);
    expect(s.say).toBe("hint");
  });

  it("starts with the official parcel", () => {
    expect(ALL_TOOLS[0]).toBe("parcel");
  });

  it("says to find the field first while the map is too far out", () => {
    expect(step({ closeEnough: false }).say).toBe("find");
  });

  it("says what it is doing while it looks, and what went wrong after", () => {
    expect(step({ searching: true, hasNotice: true }).say).toBe("searching");
    expect(step({ hasNotice: true }).say).toBe("notice");
  });
});

describe("step 2: adjusting the shape", () => {
  const shaped = { hasShape: true };

  it("shows the adjust bar and saving, and no tools or search", () => {
    const s = step(shaped);
    expect(s.phase).toBe("adjust");
    expect(s.editBar && s.save).toBe(true);
    expect(s.tools).toEqual([]);
    expect(s.search).toBe(false);
  });

  it("does not ask to find the field once there is one", () => {
    expect(step({ ...shaped, closeEnough: false }).say).toBe("hint");
  });

  it("shows the ways to draw a zone while adding, and hides saving", () => {
    const s = step({ ...shaped, mode: "add" });
    expect(s.tools).toEqual(ALL_TOOLS);
    expect(s.save).toBe(false);
    expect(s.editBar).toBe(true);
  });

  it("offers only drawing tools to take a zone out", () => {
    expect(step({ ...shaped, mode: "remove" }).tools).toEqual([
      "trace",
      "corners",
    ]);
    expect(toolsFor("remove", true)).not.toContain("parcel");
    expect(toolsFor("remove", false)).toContain("parcel");
  });
});

describe("redrawing a saved field", () => {
  it("keeps its own flow: no adjust bar or search, saving once the piece is drawn", () => {
    const s = step({ editingSaved: true, hasShape: true });
    expect(s.editBar).toBe(false);
    expect(s.search).toBe(false);
    expect(s.save).toBe(true);
    expect(step({ editingSaved: true }).tools).toEqual(ALL_TOOLS);
  });
});

describe("taking an edit back", () => {
  const shape = (n: number): Shape => ({
    type: "Polygon",
    coordinates: [
      [
        [n, 0],
        [n, 1],
        [n + 1, 1],
        [n, 0],
      ],
    ],
  });

  it("returns the shapes newest first and then nothing", () => {
    let history = pushed(pushed([], shape(1)), shape(2));
    const first = popped(history);
    expect(first.shape).toEqual(shape(2));
    history = first.history;
    expect(popped(history).shape).toEqual(shape(1));
    expect(popped(popped(history).history).shape).toBeNull();
  });

  it("remembers only the last 30 edits", () => {
    let history = pushed([], shape(0));
    for (let i = 1; i <= 40; i++) history = pushed(history, shape(i));
    expect(history).toHaveLength(30);
    expect(history[0]).toEqual(shape(11));
  });
});
