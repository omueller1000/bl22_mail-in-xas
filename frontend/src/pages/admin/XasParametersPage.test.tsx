import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { XasParameter } from "../../api/client";
import { json, mockApi } from "../../test/mockApi";
import { renderWithProviders } from "../../test/render";
import { XasParametersPage } from "./XasParametersPage";

function param(overrides: Partial<XasParameter>): XasParameter {
  return {
    name: "rbkg",
    group: "Background",
    label: "R_bkg",
    unit: "Å",
    minimum: 0.2,
    maximum: 5,
    integer: false,
    none_means: null,
    value: 1,
    default: 1,
    ...overrides,
  };
}

const DEFAULTS = [
  param({ name: "pre_order", group: "Normalisation", label: "Pre-edge polynomial order", unit: "", minimum: 0, maximum: 3, integer: true, value: 2, default: 2 }),
  param({}),
  param({ name: "bkg_kmax", label: "Fit to k", unit: "1/Å", minimum: 1, maximum: 30, none_means: "end of the data", value: null, default: null }),
];

function setup(initial: XasParameter[] = DEFAULTS) {
  let current = initial;
  const fetchMock = mockApi({
    "GET /admin/xas-parameters": () => json(current),
    "PUT /admin/xas-parameters": async (request) => {
      const { values } = (await request.clone().json()) as { values: Record<string, number | null> };
      current = current.map((p) => ({ ...p, value: values[p.name] ?? null }));
      return json(current);
    },
    "DELETE /admin/xas-parameters": () => {
      current = DEFAULTS;
      return json(current);
    },
  });
  renderWithProviders(<XasParametersPage />);
  return fetchMock;
}

const sent = async (fetchMock: ReturnType<typeof mockApi>, method: string) => {
  const request = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === method)!;
  return request.clone().json();
};

describe("XasParametersPage", () => {
  it("lists the parameters by group with their defaults", async () => {
    setup();
    expect(await screen.findByText("Normalisation")).toBeInTheDocument();
    expect(screen.getByText("Background")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /R_bkg/ })).toHaveValue("1");
    // Default and allowed values of the optional "Fit to k".
    const row = screen.getByRole("row", { name: /Fit to k/ });
    expect(within(row).getByText("end of the data")).toBeInTheDocument();
    expect(within(row).getByText(/or empty/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Restore defaults" })).toBeDisabled();
  });

  it("applies changed values", async () => {
    const fetchMock = setup();
    const user = userEvent.setup();
    const rbkg = await screen.findByRole("textbox", { name: /R_bkg/ });
    await user.clear(rbkg);
    await user.type(rbkg, "1.3");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(async () =>
      expect(await sent(fetchMock, "PUT")).toEqual({
        values: { pre_order: 2, rbkg: 1.3, bkg_kmax: null },
      }),
    );
    expect(await screen.findByText("changed")).toBeInTheDocument();
  });

  it("restores the defaults after confirmation", async () => {
    const fetchMock = setup([DEFAULTS[0]!, param({ value: 1.5 }), DEFAULTS[2]!]);
    const user = userEvent.setup();
    expect(await screen.findByText("changed")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Restore defaults" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Restore defaults" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([r]) => r.method === "DELETE")).toBe(true),
    );
    await waitFor(() => expect(screen.queryByText("changed")).not.toBeInTheDocument());
  });
});
