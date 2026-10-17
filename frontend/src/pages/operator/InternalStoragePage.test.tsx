import { screen, waitFor, within } from "@testing-library/react";
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
    since: "2026-10-13T14:05:00Z",
    edges: ["Cu K", "Ta L3"],
    measurements: { pending: 2, done: 3, error: 0 },
    failed: [],
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
    has_data: false,
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
    expect(await screen.findByLabelText("Container 0 slot 0: AAAA-AAAA")).toBeInTheDocument();

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

  it("marks unlocked frames in the grid as a warning", async () => {
    mockApi({
      "GET /storage/internal": () =>
        json([
          STORED[0],
          { ...STORED[0], barcode: "BBBB-BBBB", slot: 1, locked: false },
        ]),
    });
    renderWithProviders(<InternalStoragePage />);
    const unlocked = await screen.findByLabelText("Container 0 slot 1: BBBB-BBBB");
    expect(within(unlocked).getByText("not locked")).toBeInTheDocument();
    const locked = screen.getByLabelText("Container 0 slot 0: AAAA-AAAA");
    expect(within(locked).queryByText("not locked")).not.toBeInTheDocument();
  });

  it("lists stored frames with their slot and edges", async () => {
    mockApi({ "GET /storage/internal": () => json(STORED) });
    renderWithProviders(<InternalStoragePage />);
    const table = await screen.findByRole("table", { name: "Frames in internal storage" });
    expect(table).toHaveTextContent("AAAA-AAAA");
    expect(table).toHaveTextContent("Ada Test");
    expect(table).toHaveTextContent("Cu K, Ta L3");
    expect(table).toHaveTextContent("2026"); // in storage since
    expect(within(table).getByLabelText("yes")).toBeInTheDocument(); // locked
  });

  it("moves a stored frame to external storage from its slot", async () => {
    const fetchMock = mockApi({
      "GET /storage/internal": () => json(STORED),
      "POST /scans/apply": () =>
        json([
          {
            barcode: "AAAA-AAAA",
            current_state: "internal_storage",
            owner: "Ada Test",
            safe: true,
            locked: true,
            target_state: "external_storage",
            problem: null,
            warning: null,
            moved: true,
          },
        ]),
    });
    renderWithProviders(<InternalStoragePage />);
    await userEvent.click(await screen.findByRole("button", { name: "move AAAA-AAAA to external storage" }));

    expect(await screen.findByText("AAAA-AAAA moved to external storage")).toBeInTheDocument();
    const post = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "POST")!;
    expect(await post.json()).toEqual({ action: "external_storage", barcodes: ["AAAA-AAAA"] });
  });

  it("releases a loaded frame back into its slot", async () => {
    const fetchMock = mockApi({
      "GET /storage/internal": () => json([{ ...STORED[0], state: "loaded" }]),
      "POST /frames/AAAA-AAAA/release": () => json(frame("internal_storage")),
    });
    renderWithProviders(<InternalStoragePage />);
    expect(screen.queryByRole("button", { name: /to external storage/ })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "release AAAA-AAAA back into its slot" }));
    const dialog = await screen.findByRole("dialog", { name: "Release frame" });
    expect(dialog).toHaveTextContent("container 0, slot 0");
    expect(fetchMock.mock.calls.some(([r]) => r.url.endsWith("/release"))).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: "Release" }));

    expect(await screen.findByText("AAAA-AAAA released back into its slot")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([r]) => r.url.endsWith("/frames/AAAA-AAAA/release"))).toBe(true);
  });

  it("flags frames with failed measurements and lists them on hover", async () => {
    const failing: StoredFrame = {
      ...STORED[0]!,
      barcode: "FFFF-FFFF",
      slot: 1,
      measurements: { pending: 1, done: 2, error: 1 },
      failed: [
        {
          position: "Left-B",
          number: 2,
          technique: "xanes",
          element: "Ta",
          edge: "L1",
          message: "Edge step too small",
        },
      ],
    };
    mockApi({ "GET /storage/internal": () => json([...STORED, failing]) });
    renderWithProviders(<InternalStoragePage />);

    const slot = await screen.findByLabelText("Container 0 slot 1: FFFF-FFFF");
    expect(slot).toHaveStyle({ background: "var(--mantine-color-red-light)" });
    expect(screen.getByLabelText("Container 0 slot 0: AAAA-AAAA")).not.toHaveStyle({
      background: "var(--mantine-color-red-light)",
    });
    await userEvent.hover(within(slot).getByText("1 failed"));
    expect(
      await screen.findByText("Left-B #2 · XANES · Ta L1: Edge step too small"),
    ).toBeInTheDocument();

    const table = screen.getByRole("table", { name: "Frames in internal storage" });
    const row = within(table).getByRole("row", { name: /FFFF-FFFF/ });
    expect(within(row).getByText("2 done")).toBeInTheDocument();
    expect(within(row).getByText("1 failed")).toBeInTheDocument();
    expect(within(row).getByText("· 1 pending")).toBeInTheDocument();
    const okRow = within(table).getByRole("row", { name: /AAAA-AAAA/ });
    expect(within(okRow).queryByText(/failed/)).not.toBeInTheDocument();
  });
});
