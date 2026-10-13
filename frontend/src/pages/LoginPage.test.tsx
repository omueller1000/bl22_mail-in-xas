import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { json, meResponse, mockApi } from "../test/mockApi";
import { renderWithProviders, withProbes } from "../test/render";
import { LoginPage } from "./LoginPage";

function renderLogin(route = "/login") {
  return renderWithProviders(withProbes("/login", <LoginPage />), { route });
}

describe("LoginPage", () => {
  it("links to ORCID with the page to return to", async () => {
    mockApi({ "GET /auth/me": () => json(meResponse({})) });
    renderLogin("/login?return_to=%2Faccount");

    const link = await screen.findByRole("link", { name: "Sign in with ORCID" });
    const url = new URL(link.getAttribute("href")!);
    expect(url.pathname).toBe(`${import.meta.env.BASE_URL}api/auth/orcid/login`);
    expect(url.searchParams.get("return_to")).toBe("/account");
  });

  it("ignores return targets on other sites", async () => {
    mockApi({ "GET /auth/me": () => json(meResponse({})) });
    renderLogin("/login?return_to=%2F%2Fevil.example");

    const link = await screen.findByRole("link", { name: "Sign in with ORCID" });
    expect(new URL(link.getAttribute("href")!).searchParams.get("return_to")).toBe("/");
  });

  it("explains login errors", async () => {
    mockApi({ "GET /auth/me": () => json(meResponse({})) });
    renderLogin("/login?error=orcid_cancelled");
    expect(await screen.findByText("The ORCID login was cancelled.")).toBeInTheDocument();
  });

  it("hides the dev login unless the server enables it", async () => {
    mockApi({ "GET /auth/me": () => json(meResponse({ dev_login_enabled: false })) });
    renderLogin();
    await screen.findByRole("link", { name: "Sign in with ORCID" });
    expect(screen.queryByRole("button", { name: "Dev login" })).not.toBeInTheDocument();
  });

  it("dev login sends new users to registration, with the CSRF header", async () => {
    const fetchMock = mockApi({
      "GET /auth/me": () => json(meResponse({ dev_login_enabled: true })),
      "POST /auth/dev-login": () =>
        json(meResponse({ status: "registration_required", orcid: "0000-0002-1825-0097" })),
    });
    renderLogin();

    await userEvent.click(await screen.findByRole("button", { name: "Dev login" }));

    expect(await screen.findByTestId("location")).toHaveTextContent("/register");
    const post = fetchMock.mock.calls.map(([request]) => request).find((r) => r.method === "POST")!;
    expect(post.headers.get("X-Requested-With")).toBe("ht-xas");
    expect(await post.json()).toMatchObject({ orcid: "0000-0002-1825-0097", role: "user" });
  });
});
