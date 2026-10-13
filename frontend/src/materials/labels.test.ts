import { describe, expect, it } from "vitest";

import { frameStateColor } from "./labels";

describe("frameStateColor", () => {
  it("marks frames on hold red and leaves other states at the default colour", () => {
    expect(frameStateColor("received_on_hold")).toBe("red");
    expect(frameStateColor("received")).toBeUndefined();
    expect(frameStateColor("internal_storage")).toBeUndefined();
  });
});
