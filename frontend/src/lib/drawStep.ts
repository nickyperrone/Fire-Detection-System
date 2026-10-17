import type { Shape } from "./shapeOps";

/** How a shape is marked. The first is the default: the official parcel is one tap and exact. */
export type DrawTool = "parcel" | "detect" | "trace" | "corners";
export const ALL_TOOLS: DrawTool[] = ["parcel", "detect", "trace", "corners"];

/** What the person is doing with a shape that is already there: moving its corners, or drawing
 * a zone to add to it or take out of it. */
export type EditMode = "move" | "add" | "remove";

export type StepInput = {
  hasShape: boolean;
  /** Redrawing a saved field's outline (the server does the adding and removing). */
  editingSaved: boolean;
  mode: EditMode;
  searching: boolean;
  closeEnough: boolean;
  hasNotice: boolean;
};

export type Step = {
  /** "choose": nothing marked yet. "adjust": a shape to fix, then save. */
  phase: "choose" | "adjust";
  /** The ways to mark that make sense right now; empty when none are needed. */
  tools: DrawTool[];
  /** The place search: only while looking for the field. */
  search: boolean;
  /** Move corners, add a zone, remove a zone, undo, start over. */
  editBar: boolean;
  /** Name and Save: not while a zone is being drawn, which would hide what saving saves. */
  save: boolean;
  /** What the line under the title says. */
  say: "find" | "searching" | "notice" | "hint";
};

/** The tools for a zone: taking one out has no official parcel or satellite outline to tap. */
export function toolsFor(mode: EditMode, hasShape: boolean): DrawTool[] {
  return hasShape && mode === "remove" ? ["trace", "corners"] : ALL_TOOLS;
}

/** Everything the drawing card shows is decided here, so it can be tested without a map. */
export function stepOf(s: StepInput): Step {
  const drawingZone = s.hasShape && s.mode !== "move" && !s.editingSaved;
  const phase = s.hasShape ? "adjust" : "choose";
  return {
    phase,
    tools: !s.hasShape || drawingZone ? toolsFor(s.mode, s.hasShape) : [],
    search: !s.hasShape && !s.editingSaved,
    editBar: s.hasShape && !s.editingSaved,
    save: s.hasShape && !drawingZone,
    say: s.searching
      ? "searching"
      : s.hasNotice
        ? "notice"
        : !s.hasShape && !s.closeEnough && !s.editingSaved
          ? "find"
          : "hint",
  };
}

/** The shapes before each edit, newest last, so an edit can be taken back. */
export type History = Shape[];
const MAX_HISTORY = 30;

export function pushed(history: History, before: Shape): History {
  return [...history, before].slice(-MAX_HISTORY);
}

export function popped(history: History): {
  history: History;
  shape: Shape | null;
} {
  return {
    history: history.slice(0, -1),
    shape: history.length ? history[history.length - 1] : null,
  };
}
