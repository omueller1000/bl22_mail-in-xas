import { describe, expect, it } from "vitest";

import type { PlateType } from "../api/client";
import { frameRange, MAX_FRAMES_PER_REQUEST } from "./plates";

const TYPES: PlateType[] = [
  { id: "8-circle", name: "8-Circle", positions: [], sides: ["left", "right"], blocks_other_side: false },
  { id: "6-circle-gas", name: "6-Circle-Gas", positions: [], sides: ["left"], blocks_other_side: true },
];

describe("frameRange", () => {
  it("fits two ordinary plates per frame", () => {
    expect(frameRange(TYPES, { "8-circle": 3 })).toEqual([2, 3]);
  });

  it("gives each gas plate a frame of its own", () => {
    expect(frameRange(TYPES, { "6-circle-gas": 2, "8-circle": 2 })).toEqual([3, 4]);
  });

  it("allows frames without plates", () => {
    expect(frameRange(TYPES, {})).toEqual([1, MAX_FRAMES_PER_REQUEST]);
  });
});
