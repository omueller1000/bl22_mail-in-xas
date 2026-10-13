import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Frame, StoredFrame } from "../../api/client";
import { json, mockApi } from "../../test/mockApi";
import { renderWithProviders } from "../../test/render";
import { InternalStoragePage } from "./InternalStoragePage";

const STORED: StoredFrame[] = [
  {
    barcode: "AAAA-AAAA",
    container: 0,
    slot: 0,
    state: "internal_storage",
    owner: { id: "u1", name: "Ada Test", orcid: "0000-0002-1825-0097" },
    safe: true,
    locked: true,
    pending_measurements: 2,
  },
];

function frame(state: Frame["state"]): Frame {
  return {
    barcode: "CCCC-CCCC",
    state,
    owner: { id: "u1", name: "Ada Test", orcid: "0000-0002-1825-0097" },
    note: "",
    plates: { left: "8-circle", right: null },
    positions: [],
    safety: { at: "2026-10-13T00:00:00Z", by: "Ada Test" },
    locked: true,
    storage: null,
    missing: [],
    version: 3,
    created_at: "2026-10-12T00:00:00Z",
    updated_at: "2026-10-12T00:00:00Z",
    history: [],
  };
}

async function scan(code: string) {
  await userEvent.type(await screen.findByRole("textbox", { name: "Scan frame" }), `${code}{Enter}`);
}

describe("InternalStoragePage", () => {
  it("stores a scanned frame in a free slot", async () => {
    const fetchMock = mockApi({
      "GET /storage/internal": () => json(STORED),
      "GET /frames/CCCC-CCCC": () => json(frame("received")),
      "POST /frames/CCCC-CCCC/internal-storage": () =>
        json({ ...frame("internal_storage"), storage: { container: 0, slot: 3 } }),
    });
    renderWithProviders(<InternalStoragePage />);
    expect(await screen.findByRole("button", { name: "Container 0 slot 0: AAAA-AAAA" })).toBeDisabled();

    await scan("CCCC-CCCC");
    expect(await screen.findByText("Received")).toBeInTheDocument();
    // Pick a free slot in the grid.
    await userEvent.click(screen.getByRole("button", { name: "Container 0 slot 3: free" }));
    await userEvent.click(screen.getByRole("button", { name: "Store" }));

    expect(await screen.findByText("CCCC-CCCC stored in container 0, slot 3")).toBeInTheDocument();
    const post = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "POST")!;
    expect(await post.json()).toEqual({ container: 0, slot: 3 });
  });

  it("refuses frames that are not at the facility", async () => {
    mockApi({
      "GET /storage/internal": () => json([]),
      "GET /frames/CCCC-CCCC": () => json(frame("shipped_to_user")),
    });
    renderWithProviders(<InternalStoragePage />);
    await scan("CCCC-CCCC");
    expect(await screen.findByText(/Only received frames/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Store" })).not.toBeInTheDocument());
  });

  it("lists stored frames with their slot", async () => {
    mockApi({ "GET /storage/internal": () => json(STORED) });
    renderWithProviders(<InternalStoragePage />);
    const table = await screen.findByRole("table", { name: "Frames in internal storage" });
    expect(table).toHaveTextContent("AAAA-AAAA");
    expect(table).toHaveTextContent("Ada Test");
  });
});
