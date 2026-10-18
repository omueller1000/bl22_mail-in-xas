import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Frame } from "../api/client";
import { json, mockApi, TEST_USER } from "../test/mockApi";
import { renderWithProviders } from "../test/render";
import { FramesPage } from "./FramesPage";

function frame(barcode: string, overrides: Partial<Frame> = {}): Frame {
  return {
    barcode,
    state: "internal_storage",
    owner: { id: TEST_USER.id, name: TEST_USER.name, orcid: TEST_USER.orcid },
    note: "",
    plates: { left: null, right: null },
    positions: [],
    safety: null,
    locked: true,
    storage: null,
    missing: [],
    has_data: false,
    version: 1,
    created_at: "2026-10-12T00:00:00Z",
    updated_at: "2026-10-12T00:00:00Z",
    history: [],
    ...overrides,
  };
}

describe("FramesPage", () => {
  it("shows the data icon only for frames with data", async () => {
    mockApi({
      "GET /frames": () =>
        json([frame("AAAA-AAAA", { has_data: true }), frame("BBBB-BBBB")]),
      "GET /plate-types": () => json([]),
    });
    renderWithProviders(<FramesPage />);

    expect(await screen.findByRole("link", { name: "Data of AAAA-AAAA" })).toHaveAttribute(
      "href",
      "/frames/AAAA-AAAA/data",
    );
    expect(screen.getByRole("link", { name: "BBBB-BBBB" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Data of BBBB-BBBB" })).not.toBeInTheDocument();
    // In its own column, not next to the barcode.
    expect(screen.getByRole("columnheader", { name: "Data" })).toBeInTheDocument();
    const dataCell = screen.getByRole("link", { name: "Data of AAAA-AAAA" }).closest("td");
    expect(dataCell).not.toBe(screen.getByRole("link", { name: "AAAA-AAAA" }).closest("td"));
  });
});
