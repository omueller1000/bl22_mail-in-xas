import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Frame } from "../../api/client";
import { json, mockApi, TEST_USER } from "../../test/mockApi";
import { renderWithProviders } from "../../test/render";
import { AllFramesPage } from "./AllFramesPage";

const FRAME: Frame = {
  barcode: "AAAA-AAAA",
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
  version: 3,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-12T00:00:00Z",
  history: [
    { state: "issued", at: "2026-10-01T12:00:00Z", by: "Olaf Operator" },
    { state: "internal_storage", at: "2026-10-05T12:00:00Z", by: "Olaf Operator" },
    { state: "scheduled", at: "2026-10-06T12:00:00Z", by: "Control software" },
    { state: "internal_storage", at: "2026-10-07T12:00:00Z", by: "Control software" },
  ],
};

describe("AllFramesPage", () => {
  it("shows when each frame entered its current status", async () => {
    mockApi({
      "GET /frames": () => json([FRAME]),
      "GET /plate-types": () => json([]),
    });
    renderWithProviders(<AllFramesPage />);

    const row = await screen.findByRole("row", { name: /AAAA-AAAA/ });
    // The latest time it became "internal storage", not the first.
    const since = within(row).getByText(new Date("2026-10-07T12:00:00Z").toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }));
    await userEvent.hover(since);
    expect(await screen.findByText(/by Control software/)).toBeInTheDocument();
  });
});
