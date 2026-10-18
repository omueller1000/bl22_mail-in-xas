import { describe, expect, it } from "vitest";

import { barcodeProblem, checkLetter } from "./barcodes";

describe("barcodes", () => {
  it("computes the same check letter as the backend", () => {
    expect(checkLetter("AAAAA")).toBe("A");
    expect(checkLetter("KQZTB")).toBe("W");
  });

  it("accepts new codes with a matching check letter and old codes", () => {
    expect(barcodeProblem("KQZ-TBW")).toBeNull();
    expect(barcodeProblem("ABCD-EFGH")).toBeNull();
  });

  it("catches typos and wrong formats", () => {
    expect(barcodeProblem("KQZ-TBM")).toMatch(/check letter does not match/);
    expect(barcodeProblem("KQX-TBW")).toMatch(/check letter does not match/);
    expect(barcodeProblem("KQZTBW")).toMatch(/format ABC-DEF/);
  });
});
