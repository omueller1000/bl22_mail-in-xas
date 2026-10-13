import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { json, mockApi } from "../test/mockApi";
import { renderWithProviders } from "../test/render";
import { WarningsCard } from "./WarningsCard";

const WARNINGS = [
  {
    barcode: "AAAA-AAAA",
    owner: { id: "u1", name: "Ada Test", orcid: "0000-0002-1825-0097" },
    kind: "on_hold",
    message: "Received but not declared safe: on hold, will not be measured",
  },
];

describe("WarningsCard", () => {
  it("shows the user's warnings with links to the frames", async () => {
    const fetchMock = mockApi({ "GET /warnings": () => json(WARNINGS) });
    renderWithProviders(<WarningsCard />);
    expect(await screen.findByText("Your frames need attention")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AAAA-AAAA" })).toHaveAttribute("href", "/frames/AAAA-AAAA");
    expect(screen.queryByText("Ada Test")).not.toBeInTheDocument();
    expect(new URL(fetchMock.mock.calls[0]![0].url).searchParams.get("all_users")).toBe("false");
  });

  it("shows everyone's warnings with user names for operators", async () => {
    const fetchMock = mockApi({ "GET /warnings": () => json(WARNINGS) });
    renderWithProviders(<WarningsCard allUsers />);
    expect(await screen.findByText("Frames needing attention")).toBeInTheDocument();
    expect(screen.getByText("Ada Test")).toBeInTheDocument();
    expect(new URL(fetchMock.mock.calls[0]![0].url).searchParams.get("all_users")).toBe("true");
  });

  it("shows nothing without warnings", async () => {
    const fetchMock = mockApi({ "GET /warnings": () => json([]) });
    renderWithProviders(<WarningsCard />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/attention/)).not.toBeInTheDocument();
  });
});
