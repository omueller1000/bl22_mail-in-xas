import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ScannedFrame, ScanResult } from "../../api/client";
import { json, mockApi } from "../../test/mockApi";
import { renderWithProviders } from "../../test/render";
import { ScanPage } from "./ScanPage";

/** AAAA-AAAA has been shipped (can be received or voided); BBBB-BBBB is unknown. */
function lookup(barcode: string): ScannedFrame {
  if (barcode !== "AAAA-AAAA") {
    return {
      barcode,
      current_state: null,
      owner: null,
      safe: false,
      locked: false,
      actions: (["receive", "external_storage", "return", "void"] as const).map((action) => ({
        action,
        target_state: null,
        problem: "Unknown barcode",
        warning: null,
      })),
    };
  }
  return {
    barcode,
    current_state: "shipped_to_user",
    owner: "Ada Test",
    safe: true,
    locked: false,
    actions: [
      { action: "receive", target_state: "received", problem: null, warning: "Not locked" },
      {
        action: "external_storage",
        target_state: null,
        problem: "Not possible from state shipped_to_user",
        warning: null,
      },
      {
        action: "return",
        target_state: null,
        problem: "Not possible from state shipped_to_user",
        warning: null,
      },
      { action: "void", target_state: "void", problem: null, warning: null },
    ],
  };
}

function applied(barcode: string, action: string): ScanResult {
  return {
    barcode,
    current_state: "shipped_to_user",
    owner: "Ada Test",
    safe: true,
    locked: false,
    target_state: action === "void" ? "void" : "received",
    problem: null,
    warning: action === "receive" ? "Not locked" : null,
    moved: true,
  };
}

function mockScanApi() {
  return mockApi({
    "POST /scans/lookup": async (request) => {
      const body = (await request.clone().json()) as { barcodes: string[] };
      return json(body.barcodes.map(lookup));
    },
    "POST /scans/apply": async (request) => {
      const body = (await request.clone().json()) as { action: string; barcodes: string[] };
      return json(body.barcodes.map((code) => applied(code, body.action)));
    },
  });
}

async function scan(code: string) {
  await userEvent.type(screen.getByRole("textbox", { name: "Scan barcode" }), `${code}{Enter}`);
}

const scannedTable = () => screen.getByRole("table", { name: "Scanned frames" });

describe("ScanPage", () => {
  it("offers only the actions possible for each frame", async () => {
    mockScanApi();
    renderWithProviders(<ScanPage />);
    await scan("AAAA-AAAA");
    await scan("BBBB-BBBB");
    await within(await screen.findByRole("table", { name: "Scanned frames" })).findByText("Unknown barcode");

    expect(screen.getByRole("button", { name: "Receive AAAA-AAAA" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "External storage AAAA-AAAA" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Return to user AAAA-AAAA" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Void AAAA-AAAA" })).toBeEnabled();
    for (const label of ["Receive", "External storage", "Return to user", "Void"]) {
      expect(screen.getByRole("button", { name: `${label} BBBB-BBBB` })).toBeDisabled();
    }
  });

  it("moves a frame with its action button into the done table", async () => {
    const fetchMock = mockScanApi();
    renderWithProviders(<ScanPage />);
    await scan("AAAA-AAAA");

    await userEvent.click(await screen.findByRole("button", { name: "Receive AAAA-AAAA" }));

    const done = await screen.findByRole("table", { name: "Done" });
    expect(within(done).getByText("AAAA-AAAA")).toBeInTheDocument();
    expect(within(done).getByText("Not locked")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("table", { name: "Scanned frames" })).not.toBeInTheDocument());

    const apply = fetchMock.mock.calls.map(([r]) => r).find((r) => r.url.endsWith("/scans/apply"))!;
    expect(await apply.json()).toEqual({ action: "receive", barcodes: ["AAAA-AAAA"] });
  });

  it("asks before voiding a frame", async () => {
    const fetchMock = mockScanApi();
    renderWithProviders(<ScanPage />);
    await scan("AAAA-AAAA");

    await userEvent.click(await screen.findByRole("button", { name: "Void AAAA-AAAA" }));
    const dialog = await screen.findByRole("dialog", { name: "Void frame" });
    expect(fetchMock.mock.calls.some(([r]) => r.url.endsWith("/scans/apply"))).toBe(false);

    await userEvent.click(within(dialog).getByRole("button", { name: "Void" }));
    const done = await screen.findByRole("table", { name: "Done" });
    // Action column and new state
    expect(within(done).getAllByText("Void")).toHaveLength(2);
  });

  it("removes a scanned frame without acting on it", async () => {
    mockScanApi();
    renderWithProviders(<ScanPage />);
    await scan("AAAA-AAAA");
    await scan("BBBB-BBBB");
    await within(await screen.findByRole("table", { name: "Scanned frames" })).findByText("BBBB-BBBB");

    await userEvent.click(screen.getByRole("button", { name: "Remove BBBB-BBBB" }));
    expect(within(scannedTable()).queryByText("BBBB-BBBB")).not.toBeInTheDocument();
    expect(within(scannedTable()).getByText("AAAA-AAAA")).toBeInTheDocument();
  });
});
