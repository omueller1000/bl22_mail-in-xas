import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { json, meResponse, mockApi, TEST_USER } from "../test/mockApi";
import { renderWithProviders } from "../test/render";
import { UsersPage } from "./UsersPage";

const ADMIN = { ...TEST_USER, id: "admin", name: "Ann Admin", role: "admin" as const };

function queries(fetchMock: ReturnType<typeof mockApi>) {
  return fetchMock.mock.calls
    .map(([request]) => new URL(request.url))
    .filter((url) => url.pathname.endsWith("/users"))
    .map((url) => Object.fromEntries(url.searchParams));
}

describe("UsersPage", () => {
  it("sorts by affiliation and filters by role on the server", async () => {
    const fetchMock = mockApi({
      "GET /auth/me": () => json(meResponse({ status: "authenticated", user: ADMIN })),
      "GET /users": () => json({ items: [ADMIN, TEST_USER], total: 2, page: 1, page_size: 50 }),
    });
    renderWithProviders(<UsersPage />);

    expect(await screen.findByText("Ada Test")).toBeInTheDocument();
    // Admins change other users' roles, not their own.
    expect(screen.getByRole("combobox", { name: "Role of Ada Test" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Role of Ann Admin" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Sort by Affiliation" }));
    await waitFor(() =>
      expect(queries(fetchMock).at(-1)).toMatchObject({ sort: "affiliation", order: "asc" }),
    );

    await userEvent.click(screen.getByRole("combobox", { name: "Role" }));
    await userEvent.click(await screen.findByRole("option", { name: "Operator" }));
    await waitFor(() => expect(queries(fetchMock).at(-1)).toMatchObject({ role: "operator", page: "1" }));
  });
});
