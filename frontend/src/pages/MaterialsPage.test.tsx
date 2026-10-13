import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { PlateType } from "../api/client";
import { json, mockApi } from "../test/mockApi";
import { renderWithProviders } from "../test/render";
import { MaterialsPage } from "./MaterialsPage";

const PLATE_TYPES: PlateType[] = [
  { id: "8-circle", name: "8-Circle", positions: [..."ABCDEFGH"], sides: ["left", "right"], blocks_other_side: false },
  { id: "6-circle-gas", name: "6-Circle-Gas", positions: [..."ABCDEF"], sides: ["left"], blocks_other_side: true },
];

async function setNumber(label: string, value: string) {
  const input = screen.getByRole("textbox", { name: label });
  await userEvent.clear(input);
  await userEvent.type(input, value);
}

function request(number: number, state: string, barcodes: string[] = []) {
  return {
    id: `r${number}`,
    number,
    user: { id: "u1", name: "Ada Test", orcid: "0000-0002-1825-0097", email: "ada@example.org" },
    plates: [],
    frames: barcodes.length || 1,
    comment: null,
    state,
    reject_reason: null,
    barcodes,
    created_at: "2026-10-12T00:00:00Z",
    decided_at: null,
    decided_by: null,
    fulfilled_at: null,
  };
}

describe("MaterialsPage", () => {
  it("shows users their requests as being prepared until the frames are shipped", async () => {
    mockApi({
      "GET /plate-types": () => json(PLATE_TYPES),
      "GET /material-requests": () =>
        json([request(2, "issued", ["AAAA-AAAA"]), request(1, "fulfilled", ["BBBB-BBBB"])]),
    });
    renderWithProviders(<MaterialsPage />);

    expect(await screen.findByText("Being prepared")).toBeInTheDocument();
    expect(screen.getByText("Shipped")).toBeInTheDocument();
    // Barcodes only once shipped
    expect(screen.getByText("Frames: BBBB-BBBB")).toBeInTheDocument();
    expect(screen.queryByText(/AAAA-AAAA/)).not.toBeInTheDocument();
  });

  it("submits plates and frames within the allowed range", async () => {
    const fetchMock = mockApi({
      "GET /plate-types": () => json(PLATE_TYPES),
      "GET /material-requests": () => json([]),
      "POST /material-requests": () =>
        json({ id: "r1", number: 7, state: "submitted" }, 201),
    });
    renderWithProviders(<MaterialsPage />);
    await screen.findByText("8-Circle");

    await setNumber("8-Circle", "2");
    await setNumber("6-Circle-Gas", "1");
    // 1 gas plate + 2 others => between 2 and 3 frames; 1 is too few.
    await setNumber("Frames", "1");
    expect(screen.getByText("Between 2 and 3 for these plates")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit request" })).toBeDisabled();

    await setNumber("Frames", "2");
    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));

    expect(await screen.findByText("Request #7 submitted")).toBeInTheDocument();
    const post = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "POST")!;
    expect(await post.json()).toEqual({
      plates: [
        { plate_type: "8-circle", quantity: 2 },
        { plate_type: "6-circle-gas", quantity: 1 },
      ],
      frames: 2,
      comment: null,
    });
  });
});
