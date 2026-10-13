import { describe, expect, it } from "vitest";

import { hasRole } from "./roles";

describe("hasRole", () => {
  it("orders roles User < Operator < Admin", () => {
    expect(hasRole("admin", "operator")).toBe(true);
    expect(hasRole("operator", "operator")).toBe(true);
    expect(hasRole("operator", "admin")).toBe(false);
    expect(hasRole("user", "operator")).toBe(false);
  });
});
