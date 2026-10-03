import { describe, expect, it } from "vitest";

import { leadingTag } from "./tags";

describe("leading tag", () => {
  it("prefers plain labels to key:value tags", () => {
    expect(leadingTag(["crop:soy", "cliente 2", "casa"])).toBe("casa");
  });

  it("falls back to key:value tags, ignoring case", () => {
    expect(leadingTag(["zone:north", "Client:Ana"])).toBe("Client:Ana");
  });

  it("is undefined for an untagged field", () => {
    expect(leadingTag([])).toBeUndefined();
  });
});
