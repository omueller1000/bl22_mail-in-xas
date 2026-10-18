import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { json, mockApi } from "../../test/mockApi";
import { renderWithProviders } from "../../test/render";
import { BeamlinePage } from "./BeamlinePage";

const DEFAULTS = {
  energy_min: 4700,
  energy_max: 33000,
  default_min: 4700,
  default_max: 33000,
  edges_available: 140,
  edges_total: 248,
};

describe("BeamlinePage", () => {
  it("shows the range in keV and saves it in eV", async () => {
    let current = DEFAULTS;
    const fetchMock = mockApi({
      "GET /admin/beamline": () => json(current),
      "PUT /admin/beamline": async (request) => {
        current = { ...current, ...(await request.clone().json()), edges_available: 120 };
        return json(current);
      },
    });
    renderWithProviders(<BeamlinePage />);

    const max = await screen.findByRole("textbox", { name: "Maximum" });
    expect(max).toHaveValue("33 keV");
    expect(screen.getByText(/140 of 248 edges/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restore defaults" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();

    await userEvent.clear(max);
    await userEvent.type(max, "25.5");
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(screen.getByText(/120 of 248 edges/)).toBeInTheDocument());
    const put = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "PUT")!;
    expect(await put.json()).toEqual({ energy_min: 4700, energy_max: 25500 });
  });

  it("refuses a maximum below the minimum", async () => {
    mockApi({ "GET /admin/beamline": () => json(DEFAULTS) });
    renderWithProviders(<BeamlinePage />);
    const max = await screen.findByRole("textbox", { name: "Maximum" });
    await userEvent.clear(max);
    await userEvent.type(max, "3");
    expect(screen.getByText("Must be above the minimum")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });
});
