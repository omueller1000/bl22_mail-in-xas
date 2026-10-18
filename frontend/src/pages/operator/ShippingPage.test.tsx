import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ShippingGroup } from "../../api/client";
import { json, mockApi, TEST_USER } from "../../test/mockApi";
import { renderWithProviders } from "../../test/render";
import { ShippingPage } from "./ShippingPage";

const GROUP: ShippingGroup = {
  user: {
    id: TEST_USER.id,
    name: TEST_USER.name,
    orcid: TEST_USER.orcid,
    email: TEST_USER.email,
    phone: TEST_USER.phone,
    affiliation: TEST_USER.affiliation,
    shipping_address: { ...TEST_USER.shipping_address, care_of: "Chemistry Dept." },
  },
  requests: [
    {
      id: "r1",
      number: 12,
      plates: [
        { plate_type: "8-circle", quantity: 4 },
        { plate_type: "6-circle-gas", quantity: 1 },
      ],
      barcodes: ["AAAA-AAAA", "BBBB-BBBB"],
    },
  ],
  returning: [
    {
      barcode: "CCCC-CCCC",
      plates: { left: "8-circle", right: null },
      measurements: { pending: 0, done: 5, error: 0 },
    },
    {
      barcode: "DDDD-DDDD",
      plates: { left: "8-circle", right: "8-circle" },
      measurements: { pending: 3, done: 0, error: 0 },
    },
  ],
};

const PLATE_TYPES = [
  { id: "8-circle", name: "8-Circle", positions: [], sides: ["left", "right"], blocks_other_side: false },
  { id: "6-circle-gas", name: "6-Circle-Gas", positions: [], sides: ["left"], blocks_other_side: true },
];

describe("ShippingPage", () => {
  it("shows the shipping details as a table with a copy button per value", async () => {
    const user = userEvent.setup(); // provides a clipboard
    mockApi({
      "GET /frames/shipping": () => json([GROUP]),
      "GET /plate-types": () => json(PLATE_TYPES),
    });
    renderWithProviders(<ShippingPage />);

    const streetRow = (await screen.findByText("Street")).closest("tr")!;
    expect(within(streetRow).getByText("1 Example Way")).toBeInTheDocument();
    // Empty optional fields get no row.
    expect(screen.queryByText("Street (line 2)")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Copy Street" }));
    expect(await navigator.clipboard.readText()).toBe("1 Example Way");

    await user.click(screen.getByRole("button", { name: "Copy Email" }));
    expect(await navigator.clipboard.readText()).toBe("ada@example.org");
  });

  it("lists new material and returning frames and ships the whole box", async () => {
    const fetchMock = mockApi({
      "GET /frames/shipping": () => json([GROUP]),
      "GET /plate-types": () => json(PLATE_TYPES),
      "POST /frames/ship": () => json([]),
    });
    renderWithProviders(<ShippingPage />);

    const box = await screen.findByRole("table", { name: "Shipment to Ada Test" });
    expect(within(box).getByText("Material request #12")).toBeInTheDocument();
    expect(await within(box).findByText("4 × 8-Circle, 1 × 6-Circle-Gas")).toBeInTheDocument();
    expect(within(box).getByText("2 frames")).toBeInTheDocument();
    expect(within(box).getByText("Returning frames (2)")).toBeInTheDocument();
    const measured = within(box).getByText("CCCC-CCCC").closest("tr")!;
    expect(within(measured).getByText("measured")).toBeInTheDocument();
    expect(within(measured).getByText("8-Circle | empty")).toBeInTheDocument();
    const unmeasured = within(box).getByText("DDDD-DDDD").closest("tr")!;
    expect(within(unmeasured).getByText("not measured")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Mark shipped" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark as shipped" });
    expect(within(dialog).getByText(/4 frames/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Mark shipped" }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([r]) => r.method === "POST")).toBe(true));
    const post = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "POST")!;
    expect(await post.json()).toEqual({
      barcodes: ["AAAA-AAAA", "BBBB-BBBB", "CCCC-CCCC", "DDDD-DDDD"],
    });
  });
});
