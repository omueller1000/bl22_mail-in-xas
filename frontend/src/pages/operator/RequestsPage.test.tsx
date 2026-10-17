import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { MaterialRequest } from "../../api/client";
import { json, mockApi } from "../../test/mockApi";
import { renderWithProviders, withProbes } from "../../test/render";
import { RequestsPage } from "./RequestsPage";

const REQUEST: MaterialRequest = {
  id: "r1",
  number: 3,
  user: { id: "u1", name: "Ada Test", orcid: "0000-0002-1825-0097", email: "ada@example.org" },
  plates: [{ plate_type: "8-circle", quantity: 4 }],
  frames: 2,
  comment: null,
  state: "submitted",
  reject_reason: null,
  barcodes: [],
  created_at: "2026-10-12T00:00:00Z",
  decided_at: null,
  decided_by: null,
  fulfilled_at: null,
};

function queries(fetchMock: ReturnType<typeof mockApi>) {
  return fetchMock.mock.calls
    .map(([request]) => new URL(request.url))
    .filter((url) => url.pathname.endsWith("/material-requests/all"))
    .map((url) => Object.fromEntries(url.searchParams));
}

describe("RequestsPage", () => {
  it("lists open requests newest first and filters by status", async () => {
    const fetchMock = mockApi({
      "GET /material-requests/all": () =>
        json({ items: [REQUEST], total: 1, page: 1, page_size: 50 }),
      "GET /plate-types": () => json([]),
    });
    renderWithProviders(withProbes("/", <RequestsPage />));

    expect(await screen.findByText("Ada Test")).toBeInTheDocument();
    expect(queries(fetchMock)[0]).toMatchObject({ state: "submitted", sort: "number", order: "desc" });

    await userEvent.click(screen.getByText("All"));
    await waitFor(() => expect(queries(fetchMock).at(-1)).not.toHaveProperty("state"));

    await userEvent.click(screen.getByText("Ada Test"));
    expect(await screen.findByTestId("location")).toHaveTextContent("/operator/requests/r1");
  });
});
