import { screen, waitFor, within } from "@testing-library/react";
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

function page(items: Frame[], total = items.length) {
  return { items, total, page: 1, page_size: 50 };
}

/** The query parameters of the frame-list requests, in order. */
function frameQueries(fetchMock: ReturnType<typeof mockApi>) {
  return fetchMock.mock.calls
    .map(([request]) => new URL(request.url))
    .filter((url) => url.pathname.endsWith("/frames/all"))
    .map((url) => Object.fromEntries(url.searchParams));
}

describe("AllFramesPage", () => {
  it("shows when each frame entered its current status", async () => {
    mockApi({
      "GET /frames/all": () => json(page([FRAME])),
      "GET /plate-types": () => json([]),
    });
    renderWithProviders(<AllFramesPage />);

    const row = await screen.findByRole("row", { name: /AAAA-AAAA/ });
    // The latest time it became "internal storage", not the first.
    const since = within(row).getByText(new Date("2026-10-07T12:00:00Z").toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }));
    await userEvent.hover(since);
    expect(await screen.findByText(/by Control software/)).toBeInTheDocument();
  });

  it("pages, searches, filters and sorts on the server", async () => {
    const fetchMock = mockApi({
      "GET /frames/all": (request) => {
        const p = Number(new URL(request.url).searchParams.get("page"));
        const barcode = p === 2 ? "BBBB-BBBB" : "AAAA-AAAA";
        return json({ ...page([{ ...FRAME, barcode }], 120), page: p });
      },
      "GET /plate-types": () => json([]),
    });
    renderWithProviders(<AllFramesPage />);

    expect(await screen.findByText("1–1 of 120")).toBeInTheDocument();
    expect(frameQueries(fetchMock)[0]).toEqual({ page: "1", page_size: "50", sort: "barcode", order: "asc" });

    await userEvent.click(screen.getByRole("button", { name: "2" }));
    expect(await screen.findByText("BBBB-BBBB")).toBeInTheDocument();
    expect(screen.getByText("51–51 of 120")).toBeInTheDocument();

    // Searching starts again at page 1, once typing pauses.
    await userEvent.type(screen.getByRole("textbox", { name: "Search frames" }), "ada");
    await waitFor(() => expect(frameQueries(fetchMock).at(-1)).toMatchObject({ q: "ada", page: "1" }));
    expect(frameQueries(fetchMock).filter((q) => q.q)).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: "Sort by Barcode" }));
    await waitFor(() => expect(frameQueries(fetchMock).at(-1)).toMatchObject({ order: "desc" }));
    expect(screen.getByRole("columnheader", { name: /Barcode/ })).toHaveAttribute("aria-sort", "descending");
  });

  it("says when nothing matches", async () => {
    mockApi({
      "GET /frames/all": () => json(page([])),
      "GET /plate-types": () => json([]),
    });
    renderWithProviders(<AllFramesPage />);
    expect(await screen.findByText("No frames.")).toBeInTheDocument();
    expect(screen.getByText("0 in total")).toBeInTheDocument();
  });
});
