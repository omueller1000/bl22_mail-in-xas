import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { json, meResponse, mockApi, TEST_USER } from "../test/mockApi";
import { LocationProbe, renderWithProviders } from "../test/render";
import { RequireRole, RequireUser } from "./guards";

function renderProtected(route: string) {
  return renderWithProviders(
    <Routes>
      <Route element={<RequireUser />}>
        <Route path="/account" element={<div>account page</div>} />
        <Route element={<RequireRole role="operator" />}>
          <Route path="/users" element={<div>users page</div>} />
        </Route>
      </Route>
      <Route path="*" element={<LocationProbe />} />
    </Routes>,
    { route },
  );
}

describe("route guards", () => {
  it("sends anonymous visitors to login, remembering where they wanted to go", async () => {
    mockApi({ "GET /auth/me": () => json(meResponse({ status: "anonymous" })) });
    renderProtected("/account?tab=x");
    expect(await screen.findByTestId("location")).toHaveTextContent(
      "/login?return_to=%2Faccount%3Ftab%3Dx",
    );
  });

  it("sends unregistered users to registration", async () => {
    mockApi({
      "GET /auth/me": () =>
        json(meResponse({ status: "registration_required", orcid: TEST_USER.orcid })),
    });
    renderProtected("/account");
    expect(await screen.findByTestId("location")).toHaveTextContent("/register");
  });

  it("shows the page to registered users", async () => {
    mockApi({
      "GET /auth/me": () => json(meResponse({ status: "authenticated", user: TEST_USER })),
    });
    renderProtected("/account");
    expect(await screen.findByText("account page")).toBeInTheDocument();
  });

  it("blocks pages that need a higher role", async () => {
    mockApi({
      "GET /auth/me": () => json(meResponse({ status: "authenticated", user: TEST_USER })),
    });
    renderProtected("/users");
    expect(await screen.findByText("Not allowed")).toBeInTheDocument();
    expect(screen.queryByText("users page")).not.toBeInTheDocument();
  });

  it("lets operators in", async () => {
    mockApi({
      "GET /auth/me": () =>
        json(meResponse({ status: "authenticated", user: { ...TEST_USER, role: "operator" } })),
    });
    renderProtected("/users");
    expect(await screen.findByText("users page")).toBeInTheDocument();
  });
});
