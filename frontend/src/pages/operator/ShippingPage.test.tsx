import { screen, within } from "@testing-library/react";
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
  barcodes: ["AAAA-AAAA", "BBBB-BBBB"],
};

describe("ShippingPage", () => {
  it("shows the shipping details as a table with a copy button per value", async () => {
    const user = userEvent.setup(); // provides a clipboard
    mockApi({ "GET /frames/shipping": () => json([GROUP]) });
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
});
