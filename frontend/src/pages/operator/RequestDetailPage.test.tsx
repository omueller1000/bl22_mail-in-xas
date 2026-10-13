import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { MaterialRequest } from "../../api/client";
import { json, mockApi } from "../../test/mockApi";
import { renderWithProviders } from "../../test/render";
import { RequestDetailPage } from "./RequestDetailPage";

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

function frame(barcode: string, state: string) {
  return json({ barcode, state, owner: null, created_at: "", updated_at: "", history: [] });
}

async function scan(code: string) {
  await userEvent.type(screen.getByRole("textbox", { name: "Scan barcode" }), `${code}{Enter}`);
}

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/operator/requests/:requestId" element={<RequestDetailPage />} />
    </Routes>,
    { route: "/operator/requests/r1" },
  );
}

describe("request details", () => {
  it("shows the user's email with a copy button", async () => {
    const user = userEvent.setup(); // provides a clipboard
    mockApi({
      "GET /material-requests/r1": () => json(REQUEST),
      "GET /plate-types": () => json([]),
    });
    renderPage();

    const link = await screen.findByRole("link", { name: "ada@example.org" });
    expect(link).toHaveAttribute("href", "mailto:ada@example.org");
    expect(screen.queryByText(/0000-0002-1825-0097/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Copy email" }));
    expect(await navigator.clipboard.readText()).toBe("ada@example.org");
  });
});

describe("issuing frames for a request by scanning", () => {
  it("enables issuing only when exactly the requested number of reserved frames is scanned", async () => {
    const fetchMock = mockApi({
      "GET /material-requests/r1": () => json(REQUEST),
      "GET /plate-types": () => json([]),
      "GET /frames/AAAA-AAAA": () => frame("AAAA-AAAA", "reserved"),
      "GET /frames/BBBB-BBBB": () => frame("BBBB-BBBB", "issued"),
      "GET /frames/CCCC-CCCC": () => frame("CCCC-CCCC", "reserved"),
      "POST /material-requests/r1/issue": () =>
        json({ ...REQUEST, state: "issued", barcodes: ["AAAA-AAAA", "CCCC-CCCC"] }),
    });
    renderPage();
    await screen.findByText("Request #3");
    const issue = screen.getByRole("button", { name: "Issue 2 frames" });

    await scan("aaaa-aaaa"); // scanners may send lower case
    await scan("BBBB-BBBB");
    expect(await screen.findByText("Already Issued")).toBeInTheDocument();
    expect(issue).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Remove BBBB-BBBB" }));
    await scan("CCCC-CCCC");
    expect(await screen.findByText("2 of 2 ready")).toBeInTheDocument();
    expect(issue).toBeEnabled();

    await userEvent.click(issue);
    expect(await screen.findByText("2 frame(s) issued to Ada Test")).toBeInTheDocument();
    const post = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "POST")!;
    expect(await post.json()).toEqual({ barcodes: ["AAAA-AAAA", "CCCC-CCCC"] });
  });

  it("rejects input that is not a barcode", async () => {
    mockApi({
      "GET /material-requests/r1": () => json(REQUEST),
      "GET /plate-types": () => json([]),
    });
    renderPage();
    await screen.findByText("Request #3");

    await scan("hello");
    expect(screen.getByText('"HELLO" is not a barcode (format ABCD-EFGH)')).toBeInTheDocument();
  });
});
