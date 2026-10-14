import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { Frame, SweepInfo } from "../api/client";
import type { Trace } from "../data/Chart";
import { json, mockApi, TEST_USER } from "../test/mockApi";
import { renderWithProviders } from "../test/render";
import { DataPage } from "./DataPage";

// Plotly does not run in jsdom; show what would be plotted instead.
vi.mock("../data/Chart", () => ({
  Chart: ({ traces, yLabel }: { traces: Trace[]; yLabel: string }) => (
    <div data-testid="chart">
      {yLabel}: {traces.map((t) => t.name).join(", ")}
    </div>
  ),
}));

const FRAME = {
  barcode: "ABCD-EFGH",
  state: "internal_storage",
  owner: { id: TEST_USER.id, name: TEST_USER.name, orcid: TEST_USER.orcid },
  note: "",
  plates: { left: "8-circle", right: null },
  positions: [
    { position: "Left-A", sample_id: "s1", sample_name: "CuO" },
    { position: "Left-B", sample_id: "s2", sample_name: "NiO" },
  ],
  safety: null,
  locked: true,
  storage: { container: 0, slot: 1, since: null },
  missing: [],
  has_data: true,
  version: 5,
  created_at: "2026-10-12T00:00:00Z",
  updated_at: "2026-10-12T00:00:00Z",
  history: [],
} as unknown as Frame;

function sweep(sweepNo: number, batch = 1, overrides: Partial<SweepInfo> = {}): SweepInfo {
  return {
    id: `sw${sweepNo}`,
    measurement_id: "m1",
    frame: "ABCD-EFGH",
    position: "Left-A",
    number: 1,
    batch_no: batch,
    sweep_no: sweepNo,
    measured: {
      technique: "exafs",
      element: "Cu",
      edge: "K",
      detection: "transmission",
      beam: "unfocused",
    },
    points: 3,
    channels: ["energy", "i0", "i1"],
    spectra: ["sample_trans"],
    uploaded_at: "2026-10-13T00:00:00Z",
    ...overrides,
  };
}

const CURVE = { x: [1, 2, 3], y: [0.1, 0.2, 0.3] };

function processedResult(sweeps: number[], problems: string[] = []) {
  return {
    spectrum: "sample_trans",
    sweeps,
    element: "Cu",
    edge: "K",
    e0: 8979,
    e0_source: "X-Ray Data Booklet",
    edge_step: problems.length ? null : 0.52,
    mu: CURVE,
    pre_edge: CURVE,
    post_edge: CURVE,
    background: CURVE,
    chi: problems.length ? null : CURVE,
    ft_window: problems.length ? null : { x: [1, 2, 3], y: [0, 1, 0] },
    chir: problems.length ? null : { r: [1, 2], magnitude: [1, 2], real: [1, 2], imaginary: [1, 2] },
    parameters: { pre_order: 2, post_order: 3, rbkg: 1 },
    problems,
  };
}

function renderPage(
  sweeps: SweepInfo[],
  route = "/frames/ABCD-EFGH/data",
  processingProblems: string[] = [],
) {
  const fetchMock = mockApi({
    "GET /frames/ABCD-EFGH": () => json(FRAME),
    "GET /frames/ABCD-EFGH/sweeps": () => json(sweeps),
    "GET /measurement-options": () => json({ techniques: [], elements: [], edges: [], detections: [], beams: [] }),
    ...Object.fromEntries(
      sweeps.flatMap((s) => [
        [`GET /sweeps/${s.id}/curve`, () => json(CURVE)],
        [
          `GET /sweeps/${s.id}`,
          () => json({ sweep: s, metadata: { lattice_spacing: 1.92 } }),
        ],
      ]),
    ),
    "GET /measurements/m1/batches/1/merge": () => json(CURVE),
    "GET /measurements/m1/batches/1/process": (request) => {
      const numbers = new URL(request.url).searchParams.getAll("sweeps").map(Number);
      return json(processedResult(numbers, processingProblems));
    },
  });
  renderWithProviders(
    <Routes>
      <Route path="/frames/:barcode/data" element={<DataPage />} />
    </Routes>,
    { route },
  );
  return fetchMock;
}

const requested = (fetchMock: ReturnType<typeof mockApi>) =>
  fetchMock.mock.calls.map(([r]) => {
    const url = new URL(r.url);
    return url.pathname.replace(/.*\/api/, "") + url.search;
  });

describe("DataPage", () => {
  it("says when there is no data yet", async () => {
    renderPage([]);
    expect(await screen.findByText(/No data yet/)).toBeInTheDocument();
    expect(screen.queryByText(/Download/)).not.toBeInTheDocument();
  });

  it("plots the latest batch's sweeps with the spectrum matching the detection", async () => {
    const fetchMock = renderPage([sweep(1), sweep(2, 2), sweep(3, 2)]);
    expect(await screen.findByText("ln(i0/i1): Sweep 2, Sweep 3")).toBeInTheDocument();
    expect(requested(fetchMock)).toContain("/sweeps/sw2/curve?view=spectrum&name=sample_trans");
    expect(screen.getByRole("link", { name: /Download all/ })).toHaveAttribute(
      "href",
      expect.stringContaining("/frames/ABCD-EFGH/export.zip"),
    );
    // Metadata of the first sweep in the batch.
    expect(await screen.findByText("lattice_spacing")).toBeInTheDocument();
  });

  it("toggles sweeps and shows the merged curves", async () => {
    const fetchMock = renderPage([sweep(1), sweep(2), sweep(3)]);
    const user = userEvent.setup();
    await screen.findByText(/Sweep 1, Sweep 2, Sweep 3/);

    await user.click(screen.getByRole("checkbox", { name: "Sweep 2" }));
    await waitFor(() => expect(screen.getByTestId("chart")).toHaveTextContent(/: Sweep 1, Sweep 3$/));

    await user.click(screen.getByRole("switch", { name: /checked sweeps/ }));
    expect(await screen.findByText(/Merged, checked \(2\)/)).toBeInTheDocument();
    expect(requested(fetchMock)).toContain(
      "/measurements/m1/batches/1/merge?view=spectrum&name=sample_trans&sweeps=1&sweeps=3",
    );

    // Merging all sweeps includes the unchecked one.
    await user.click(screen.getByRole("switch", { name: /all sweeps/ }));
    expect(await screen.findByText(/Merged, all \(3\)/)).toBeInTheDocument();
    expect(requested(fetchMock)).toContain(
      "/measurements/m1/batches/1/merge?view=spectrum&name=sample_trans&sweeps=1&sweeps=2&sweeps=3",
    );
  });

  it("merges all sweeps even when none is checked", async () => {
    renderPage([sweep(1), sweep(2)]);
    const user = userEvent.setup();
    await screen.findByText(/Sweep 1, Sweep 2/);
    await user.click(screen.getByRole("button", { name: "None" }));
    expect(await screen.findByText(/Select at least one sweep/)).toBeInTheDocument();

    await user.click(screen.getByRole("switch", { name: /all sweeps/ }));
    expect(await screen.findByTestId("chart")).toHaveTextContent(/: Merged, all \(2\)$/);
  });

  it("opens on the position of the sample given in the link", async () => {
    const other = { measurement_id: "m2", position: "Left-B" };
    const fetchMock = renderPage(
      [sweep(1), sweep(2, 1, { ...other, id: "sw2" })],
      "/frames/ABCD-EFGH/data?sample=s2",
    );
    expect(await screen.findByText(/: Sweep 2$/)).toBeInTheDocument();
    expect(requested(fetchMock)).toContain("/sweeps/sw2/curve?view=spectrum&name=sample_trans");
  });

  it("plots mu(E) with the fitted functions of the checked sweep", async () => {
    const fetchMock = renderPage([sweep(1), sweep(2)]);
    const user = userEvent.setup();
    await screen.findByText(/Sweep 1, Sweep 2/);
    await user.click(screen.getByRole("checkbox", { name: "Sweep 2" }));
    await user.click(screen.getByRole("radio", { name: "μ(E)" }));

    expect(
      await screen.findByText("μ(E): μ(E), Pre-edge, Post-edge, Background"),
    ).toBeInTheDocument();
    expect(requested(fetchMock)).toContain(
      "/measurements/m1/batches/1/process?spectrum=sample_trans&sweeps=1",
    );
    expect(screen.getByText("Processing sweep 1.")).toBeInTheDocument();
    expect(screen.getByText(/8979 \(Cu K/)).toBeInTheDocument(); // E0 in the processing card
    expect(screen.queryByRole("checkbox", { name: "Background" })).not.toBeInTheDocument();
  });

  it("processes the merge when several sweeps are checked", async () => {
    const fetchMock = renderPage([sweep(1), sweep(2), sweep(3)]);
    const user = userEvent.setup();
    await screen.findByText(/Sweep 1, Sweep 2, Sweep 3/);
    await user.click(screen.getByRole("radio", { name: "χ(R)" }));

    expect(await screen.findByText(/: \|χ\(R\)\|$/)).toBeInTheDocument();
    expect(requested(fetchMock)).toContain(
      "/measurements/m1/batches/1/process?spectrum=sample_trans&sweeps=1&sweeps=2&sweeps=3",
    );
    expect(screen.getByText("Processing the merge of sweeps 1, 2, 3.")).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: /Merge/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Imaginary part" }));
    expect(await screen.findByText(/\|χ\(R\)\|, Im χ\(R\)$/)).toBeInTheDocument();
  });

  it("shows the FT window with chi(k)", async () => {
    renderPage([sweep(1)]);
    const user = userEvent.setup();
    await screen.findByTestId("chart");
    await user.click(screen.getByRole("radio", { name: "χ(k)" }));
    expect(await screen.findByText(/: k²χ\(k\), FT window$/)).toBeInTheDocument();
  });

  it("explains why processing is incomplete", async () => {
    renderPage([sweep(1)], undefined, ["The post-edge range contains 0 point(s)."]);
    const user = userEvent.setup();
    await screen.findByTestId("chart");
    await user.click(screen.getByRole("radio", { name: "χ(k)" }));
    expect(await screen.findByText(/post-edge range contains 0 point/)).toBeInTheDocument();
  });
});
