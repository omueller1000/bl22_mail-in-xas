import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { json, meResponse, mockApi, TEST_USER } from "../test/mockApi";
import { renderWithProviders } from "../test/render";
import { AccountPage } from "./AccountPage";
import { RegisterPage } from "./RegisterPage";

const UNCONFIRMED = { ...TEST_USER, email_confirmed: false };

describe("email confirmation", () => {
  it("asks for the emailed code after registration", async () => {
    let confirmed = false;
    const fetchMock = mockApi({
      "GET /auth/me": () =>
        json(
          meResponse({
            status: confirmed ? "authenticated" : "email_confirmation_required",
            orcid: TEST_USER.orcid,
            user: confirmed ? TEST_USER : UNCONFIRMED,
          }),
        ),
      "POST /users/me/email/confirm": () => {
        confirmed = true;
        return json(TEST_USER);
      },
    });
    renderWithProviders(<RegisterPage />);
    const user = userEvent.setup();

    expect(await screen.findByText("Confirm your email address")).toBeInTheDocument();
    expect(screen.getByText(TEST_USER.email)).toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: "Confirm" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "Confirmation code" }), "12a3456");
    expect(screen.getByRole("textbox", { name: "Confirmation code" })).toHaveValue("123456");
    await user.click(confirm);

    await waitFor(async () => {
      const request = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "POST")!;
      expect(await request.clone().json()).toEqual({ code: "123456" });
    });
  });

  it("shows a requested email change with the code form", async () => {
    mockApi({
      "GET /auth/me": () =>
        json(
          meResponse({
            status: "authenticated",
            user: { ...TEST_USER, pending_email: "new@example.org" },
          }),
        ),
    });
    renderWithProviders(<AccountPage />);
    expect(await screen.findByText("Confirm your new email address")).toBeInTheDocument();
    expect(screen.getByText("new@example.org")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep the current address" })).toBeInTheDocument();
  });
});
