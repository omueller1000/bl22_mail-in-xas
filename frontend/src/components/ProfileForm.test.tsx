import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../test/render";
import { ProfileForm } from "./ProfileForm";

async function fill(label: string | RegExp, value: string) {
  await userEvent.type(screen.getByLabelText(label), value);
}

describe("ProfileForm", () => {
  it("reports missing required fields instead of submitting", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(<ProfileForm submitLabel="Create account" submitting={false} onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(screen.getByText("Country is required")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits trimmed values, with empty optional fields as null", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(
      <ProfileForm askName submitLabel="Create account" submitting={false} onSubmit={onSubmit} />,
    );

    await fill(/^Name/, "Grace Test");
    await fill(/^Email/, "grace@example.org");
    await fill(/^Phone/, "+41 22 555 0000");
    await fill(/^Affiliation/, " Institute ");
    await fill(/^Street$|^Street \*/, "Rue Example 5");
    await fill(/^City/, "Geneva");
    await fill(/^Country/, "Switzerland");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(onSubmit).toHaveBeenCalledWith(
      {
        email: "grace@example.org",
        phone: "+41 22 555 0000",
        affiliation: "Institute",
        shipping_address: {
          care_of: null,
          street1: "Rue Example 5",
          street2: null,
          city: "Geneva",
          region: null,
          postal_code: null,
          country: "Switzerland",
        },
      },
      "Grace Test",
    );
  });
});
