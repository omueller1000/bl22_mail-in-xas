import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { json, meResponse, mockApi, TEST_USER } from "../test/mockApi";
import { LocationProbe, renderWithProviders } from "../test/render";
import { Layout } from "./Layout";

describe("Layout", () => {
  it("goes to the sign-in page after signing out", async () => {
    let signedIn = true;
    mockApi({
      "GET /auth/me": () =>
        json(signedIn ? meResponse({ status: "authenticated", user: TEST_USER, orcid: TEST_USER.orcid }) : meResponse({})),
      "POST /auth/logout": () => {
        signedIn = false;
        return new Response(null, { status: 204 });
      },
    });
    renderWithProviders(
      <Routes>
        <Route element={<Layout />}>
          <Route path="/frames" element={<div>My frames</div>} />
          <Route path="/login" element={<LocationProbe />} />
        </Route>
      </Routes>,
      { route: "/frames" },
    );

    expect(await screen.findByRole("link", { name: "My Frames" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Ada Test/ }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Sign out" }));
    expect(await screen.findByTestId("location")).toHaveTextContent("/login");
    // The navbar no longer shows the signed-in user's pages.
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "My Frames" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Ada Test/ })).not.toBeInTheDocument();
  });
});
