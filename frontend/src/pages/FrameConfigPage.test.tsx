import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { Frame, PlateType, Sample } from "../api/client";
import { json, mockApi } from "../test/mockApi";
import { renderWithProviders } from "../test/render";
import { FrameConfigPage } from "./FrameConfigPage";

const PLATE_TYPES: PlateType[] = [
  { id: "8-circle", name: "8-Circle", positions: [..."ABCDEFGH"], sides: ["left", "right"], blocks_other_side: false },
  { id: "8-slot", name: "8-Slot", positions: [..."ABCDEFGH"], sides: ["left", "right"], blocks_other_side: false },
  { id: "6-circle-gas", name: "6-Circle-Gas", positions: [..."ABCDEF"], sides: ["left"], blocks_other_side: true },
];

const SAMPLES: Sample[] = [
  { id: "s2", name: "CuO", description: "", msds: null, archived: false, frozen: false, deletable: true, frames: [], created_at: "2026-10-13T00:00:00Z", updated_at: "2026-10-13T00:00:00Z" },
  { id: "s1", name: "Fe2O3", description: "", msds: null, archived: false, frozen: false, deletable: true, frames: [], created_at: "2026-10-12T00:00:00Z", updated_at: "2026-10-12T00:00:00Z" },
];

function frame(overrides: Partial<Frame> = {}): Frame {
  return {
    barcode: "ABCD-EFGH",
    state: "shipped_to_user",
    owner: null,
    note: "",
    plates: { left: "8-circle", right: "8-circle" },
    positions: [
      { position: "Left-A", sample_id: "s1", sample_name: "Fe2O3" },
      { position: "Right-B", sample_id: "s2", sample_name: "CuO" },
    ],
    safety: null,
    locked: false,
    version: 4,
    created_at: "2026-10-12T00:00:00Z",
    updated_at: "2026-10-12T00:00:00Z",
    history: [],
    ...overrides,
  };
}

function renderPage(current: Frame, extra: Parameters<typeof mockApi>[0] = {}) {
  const fetchMock = mockApi({
    "GET /frames/ABCD-EFGH": () => json(current),
    "GET /plate-types": () => json(PLATE_TYPES),
    "GET /samples": () => json(SAMPLES),
    ...extra,
  });
  renderWithProviders(
    <Routes>
      <Route path="/frames/:barcode" element={<FrameConfigPage />} />
    </Routes>,
    { route: "/frames/ABCD-EFGH" },
  );
  return fetchMock;
}

async function lastBody(fetchMock: ReturnType<typeof mockApi>, method: string) {
  const request = fetchMock.mock.calls.map(([r]) => r).filter((r) => r.method === method).at(-1)!;
  return { url: new URL(request.url).pathname, body: await request.text() };
}

describe("FrameConfigPage", () => {
  it("draws filled and empty positions", async () => {
    renderPage(frame());
    expect(await screen.findByRole("button", { name: "Left-A: Fe2O3" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Right-B: CuO" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Left-B: empty" })).toBeInTheDocument();
    // 8 + 8 positions
    expect(screen.getAllByRole("button", { name: /^(Left|Right)-[A-H]:/ })).toHaveLength(16);
    // Colours only for filled positions, drawn below the frame and plate images.
    const fill = screen.getByTestId("sample-Left-A");
    expect(screen.queryByTestId("sample-Left-B")).not.toBeInTheDocument();
    const firstImage = document.querySelector("img")!;
    expect(fill.compareDocumentPosition(firstImage) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("places a sample by clicking an empty position", async () => {
    const fetchMock = renderPage(frame(), {
      "PUT /frames/ABCD-EFGH/positions/Left-B": () => json(frame({ version: 5 })),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Left-B: empty" }));

    const dialog = await screen.findByRole("dialog", { name: "Position Left-B" });
    await userEvent.click(within(dialog).getByRole("combobox", { name: "Sample" }));
    await userEvent.click(await screen.findByRole("option", { name: "CuO" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Place sample" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const { url, body } = await lastBody(fetchMock, "PUT");
    expect(url).toMatch(/\/frames\/ABCD-EFGH\/positions\/Left-B$/);
    expect(JSON.parse(body)).toEqual({ version: 4, sample_id: "s2" });
  });

  it("asks before a plate change removes samples", async () => {
    const fetchMock = renderPage(frame(), {
      "PUT /frames/ABCD-EFGH/plates": () =>
        json(frame({ plates: { left: "6-circle-gas", right: null }, positions: [], version: 5 })),
    });
    await userEvent.click(await screen.findByRole("combobox", { name: "Left" }));
    await userEvent.click(await screen.findByRole("option", { name: "6-Circle-Gas (whole frame)" }));

    const dialog = await screen.findByRole("dialog", { name: "Change plates" });
    expect(dialog).toHaveTextContent("Left-A, Right-B");
    await userEvent.click(within(dialog).getByRole("button", { name: "Change plates" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // The gas plate spans the frame, so the right plate is removed too.
    expect(JSON.parse((await lastBody(fetchMock, "PUT")).body)).toEqual({
      version: 4,
      left: "6-circle-gas",
      right: null,
    });
  });

  it("draws a whole-frame gas plate with six positions", async () => {
    renderPage(frame({ plates: { left: "6-circle-gas", right: null }, positions: [] }));
    await screen.findByRole("button", { name: "Left-A: empty" });
    expect(screen.getAllByRole("button", { name: /^(Left|Right)-[A-H]:/ })).toHaveLength(6);
    expect(screen.getByRole("combobox", { name: "Right" })).toBeDisabled();
  });

  it("is read-only once declared safe", async () => {
    renderPage(frame({ safety: { at: "2026-10-13T00:00:00Z", by: "Ada Test" } }));
    expect(await screen.findByText(/declared safe/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Left-B: empty" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Left" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: /Note/ })).toBeDisabled();
  });
});
