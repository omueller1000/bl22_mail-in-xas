import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { Frame, PlateType, Sample } from "../api/client";
import { json, meResponse, mockApi, TEST_USER } from "../test/mockApi";
import { renderWithProviders } from "../test/render";
import { FrameConfigPage } from "./FrameConfigPage";

const PLATE_TYPES: PlateType[] = [
  { id: "8-circle", name: "8-Circle", positions: [..."ABCDEFGH"], sides: ["left", "right"], blocks_other_side: false },
  { id: "8-slot", name: "8-Slot", positions: [..."ABCDEFGH"], sides: ["left", "right"], blocks_other_side: false },
  { id: "6-circle-gas", name: "6-Circle-Gas", positions: [..."ABCDEF"], sides: ["left"], blocks_other_side: true },
];

const SAMPLES: Sample[] = [
  { id: "s2", name: "CuO", description: "", msds: null, archived: false, frozen: false, deletable: true, frames: [], data_frames: [], created_at: "2026-10-13T00:00:00Z", updated_at: "2026-10-13T00:00:00Z" },
  { id: "s1", name: "Fe2O3", description: "", msds: null, archived: false, frozen: false, deletable: true, frames: [], data_frames: [], created_at: "2026-10-12T00:00:00Z", updated_at: "2026-10-12T00:00:00Z" },
  { id: "s3", name: "NiO", description: "", msds: null, archived: false, frozen: false, deletable: true, frames: [], data_frames: [], created_at: "2026-10-11T00:00:00Z", updated_at: "2026-10-11T00:00:00Z" },
];

const OPTIONS = {
  techniques: [
    { value: "xanes", label: "XANES" },
    { value: "exafs", label: "EXAFS" },
  ],
  // As limited by a 4.7-33 keV beamline.
  elements: [
    { symbol: "Fe", z: 26, edges: [{ edge: "K", energy: 7112 }] },
    { symbol: "Cu", z: 29, edges: [{ edge: "K", energy: 8979 }] },
    {
      symbol: "Pb",
      z: 82,
      edges: [
        { edge: "L1", energy: 15861 },
        { edge: "L2", energy: 15200 },
        { edge: "L3", energy: 13035 },
      ],
    },
  ],
  energy_min: 4700,
  energy_max: 33000,
  edges: ["K", "L1", "L2", "L3"].map((e) => ({ value: e, label: e })),
  detections: [
    { value: "transmission", label: "Transmission" },
    { value: "transmission_tfy", label: "Transmission + TFY" },
    { value: "transmission_sdd", label: "Transmission + SDD" },
  ],
  beams: [
    { value: "unfocused", label: "Unfocused" },
    { value: "focused", label: "Focused" },
  ],
};

const MEASUREMENTS = [
  {
    id: "m1",
    frame: "ABCD-EFGH",
    position: "Left-A",
    number: 1,
    technique: "xanes",
    element: "Fe",
    edge: "K",
    detection: "transmission",
    beam: "unfocused",
    status: "pending",
    error_message: null,
    executed: false,
    created_at: "2026-10-13T00:00:00Z",
    updated_at: "2026-10-13T00:00:00Z",
    changed_by: "Ada Test",
  },
];

function frame(overrides: Partial<Frame> = {}): Frame {
  return {
    barcode: "ABCD-EFGH",
    state: "shipped_to_user",
    owner: { id: TEST_USER.id, name: TEST_USER.name, orcid: TEST_USER.orcid },
    note: "",
    plates: { left: "8-circle", right: "8-circle" },
    positions: [
      { position: "Left-A", sample_id: "s1", sample_name: "Fe2O3" },
      { position: "Right-B", sample_id: "s2", sample_name: "CuO" },
    ],
    safety: null,
    locked: false,
    storage: null,
    missing: [],
    has_data: false,
    version: 4,
    created_at: "2026-10-12T00:00:00Z",
    updated_at: "2026-10-12T00:00:00Z",
    history: [],
    ...overrides,
  };
}

function renderPage(
  current: Frame,
  extra: Parameters<typeof mockApi>[0] = {},
  user: typeof TEST_USER = TEST_USER,
) {
  const fetchMock = mockApi({
    "GET /auth/me": () => json(meResponse({ status: "authenticated", user })),
    "GET /frames/ABCD-EFGH": () => json(current),
    "GET /frames/ABCD-EFGH/measurements": () => json(MEASUREMENTS),
    "GET /measurement-options": () => json(OPTIONS),
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
    const place = within(dialog).getByRole("button", { name: "Place sample" });
    expect(place).toBeDisabled();
    // CuO is already at Right-B: a sample is placed only once per frame.
    const cuo = within(dialog).getByRole("row", { name: /^CuO/ });
    expect(cuo).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(cuo);
    expect(cuo).toHaveAttribute("aria-selected", "false");

    await userEvent.click(within(dialog).getByRole("row", { name: /^NiO/ }));
    expect(within(dialog).getByRole("row", { name: /^NiO/ })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(place);

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const { url, body } = await lastBody(fetchMock, "PUT");
    expect(url).toMatch(/\/frames\/ABCD-EFGH\/positions\/Left-B$/);
    expect(JSON.parse(body)).toEqual({ version: 4, sample_id: "s3" });
  });

  it("lists samples newest first and filters them by the search text", async () => {
    renderPage(frame());
    await userEvent.click(await screen.findByRole("button", { name: "Left-B: empty" }));
    const dialog = await screen.findByRole("dialog", { name: "Position Left-B" });

    const names = () =>
      within(dialog)
        .getAllByRole("row")
        .slice(1) // header
        .map((row) => row.querySelector("td")?.textContent);
    // Samples already on this frame show their positions.
    expect(names()).toEqual(["CuO (Right-B)", "Fe2O3 (Left-A)", "NiO"]);

    await userEvent.type(within(dialog).getByRole("textbox", { name: "Search samples" }), "fe");
    expect(names()).toEqual(["Fe2O3 (Left-A)"]);
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Search samples" }), "xyz");
    expect(within(dialog).getByText("No matching sample")).toBeInTheDocument();
  });

  it("removes a sample from its position with the trash icon", async () => {
    let current = frame();
    const fetchMock = renderPage(current, {
      "GET /frames/ABCD-EFGH": () => json(current),
      "DELETE /frames/ABCD-EFGH/positions/Right-B": () => {
        current = frame({ positions: current.positions.slice(0, 1), version: 5 });
        return json(current);
      },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Remove CuO from Right-B" }));

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Remove CuO from Right-B" })).not.toBeInTheDocument(),
    );
    const request = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "DELETE")!;
    const url = new URL(request.url);
    expect(url.pathname).toMatch(/\/frames\/ABCD-EFGH\/positions\/Right-B$/);
    expect(url.searchParams.get("version")).toBe("4");
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
    expect(screen.queryByRole("button", { name: /^Remove / })).not.toBeInTheDocument();
  });
  it("lists measurements per position and adds one", async () => {
    const fetchMock = renderPage(frame(), {
      "POST /frames/ABCD-EFGH/positions/Right-B/measurements": () =>
        json({ ...MEASUREMENTS[0], id: "m2", position: "Right-B" }, 201),
    });
    expect(await screen.findByText("XANES · Fe K · Transmission · Unfocused")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();

    const addButtons = screen.getAllByRole("button", { name: "Add measurement" });
    await userEvent.click(addButtons[1]!); // Right-B
    const dialog = await screen.findByRole("dialog", { name: "New measurement at Right-B" });
    // EXAFS is the default technique; switch to XANES.
    expect(within(dialog).getByRole("radio", { name: "EXAFS" })).toBeChecked();
    await userEvent.click(within(dialog).getByText("XANES"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Add measurement" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem("ht-xas.lastElementEdge")!)).toEqual({
      element: "Fe",
      edge: "K",
    });
    localStorage.clear();
    const post = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "POST")!;
    expect(JSON.parse(await post.text())).toEqual({
      version: 4,
      technique: "xanes",
      element: "Fe",
      edge: "K",
      detection: "transmission",
      beam: "unfocused",
    });
  });

  it("explains the beam options in tooltips", async () => {
    renderPage(frame());
    await userEvent.click((await screen.findAllByRole("button", { name: "Add measurement" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: "New measurement at Left-A" });
    await userEvent.hover(within(dialog).getByText("Focused"));
    expect(await screen.findByText(/polycapillary/)).toBeInTheDocument();
  });

  it("starts new measurements with the last saved element and edge", async () => {
    localStorage.setItem("ht-xas.lastElementEdge", JSON.stringify({ element: "Pb", edge: "L2" }));
    renderPage(frame());
    await userEvent.click((await screen.findAllByRole("button", { name: "Add measurement" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: "New measurement at Left-A" });
    expect(within(dialog).getByRole("combobox", { name: "Element" })).toHaveValue("Pb (82)");
    expect(within(dialog).getByRole("radio", { name: "L2" })).toBeChecked();
    localStorage.clear();
  });

  it("falls back when the last saved edge is outside the beamline's range", async () => {
    localStorage.setItem("ht-xas.lastElementEdge", JSON.stringify({ element: "Cu", edge: "L3" }));
    renderPage(frame());
    await userEvent.click((await screen.findAllByRole("button", { name: "Add measurement" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: "New measurement at Left-A" });
    expect(within(dialog).getByRole("combobox", { name: "Element" })).toHaveValue("Cu (29)");
    expect(within(dialog).getByRole("radio", { name: "K" })).toBeChecked();
    localStorage.clear();
  });

  it("offers only the element's edges within the beamline's range", async () => {
    renderPage(frame());
    await userEvent.click((await screen.findAllByRole("button", { name: "Add measurement" }))[0]!);
    const dialog = await screen.findByRole("dialog", { name: "New measurement at Left-A" });
    expect(within(dialog).getByText("E0 = 7,112 eV")).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: "L3" })).toBeDisabled();

    await userEvent.click(within(dialog).getByRole("combobox", { name: "Element" }));
    await userEvent.click(await screen.findByRole("option", { name: "Pb (82)" }));
    // Pb K (88 keV) is out of range: the edge moves to L3.
    expect(within(dialog).getByRole("radio", { name: "L3" })).toBeChecked();
    expect(within(dialog).getByRole("radio", { name: "K" })).toBeDisabled();
    expect(within(dialog).getByText("E0 = 13,035 eV")).toBeInTheDocument();
  });

  it("lists what is missing and declares safe only after confirming", async () => {
    renderPage(frame({ missing: ["Add a measurement to Right-B"] }));
    expect(await screen.findByText("Add a measurement to Right-B")).toBeInTheDocument();
    const declare = screen.getByRole("button", { name: "Declare safe" });
    await userEvent.click(screen.getByRole("checkbox", { name: /solid and non-hazardous/ }));
    expect(declare).toBeDisabled(); // still incomplete
  });

  it("declares a complete frame safe", async () => {
    const fetchMock = renderPage(frame(), {
      "POST /frames/ABCD-EFGH/declare-safe": () =>
        json(frame({ safety: { at: "2026-10-13T00:00:00Z", by: "Ada Test" }, version: 5 })),
    });
    const declare = await screen.findByRole("button", { name: "Declare safe" });
    expect(declare).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: /solid and non-hazardous/ }));
    await userEvent.click(declare);

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([r]) => r.method === "POST")).toBe(true),
    );
    const post = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "POST")!;
    expect(JSON.parse(await post.text())).toEqual({ version: 4, confirm: true });
  });

  it("freezes measurements when locked and offers unlocking", async () => {
    renderPage(
      frame({ safety: { at: "2026-10-13T00:00:00Z", by: "Ada Test" }, locked: true }),
    );
    expect(await screen.findByText("Locked")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unlock" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Add measurement" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Edit measurement/ })).not.toBeInTheDocument();
  });

  it("lets operators edit measurements but not plates, samples or the declaration", async () => {
    const operator = { ...TEST_USER, id: "op1", name: "Olga Operator", role: "operator" as const };
    renderPage(frame(), {}, operator);
    expect(await screen.findByText(/Only the owner can change plates and samples/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Left" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /^Remove / })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add measurement" })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Declare safe" })).not.toBeInTheDocument();
  });
});
