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
      note: "",
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
    note: "Box 3, iron oxides",
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
  const moved: Record<string, ScanResult> = {};
  return mockApi({
    "POST /scans/lookup": async (request) => {
      const body = (await request.clone().json()) as { barcodes: string[] };
      return json(
        body.barcodes.map((code) => {
          const frame = lookup(code);
          const after = moved[code];
          if (!after) return frame;
          // After a move: new status, and no further action possible (enough for these tests).
          return {
            ...frame,
            current_state: after.target_state,
            actions: frame.actions.map((x) => ({ ...x, target_state: null, problem: "Done" })),
          };
        }),
      );
    },
    "POST /scans/apply": async (request) => {
      const body = (await request.clone().json()) as { action: string; barcodes: string[] };
      const results = body.barcodes.map((code) => applied(code, body.action));
      for (const r of results) moved[r.barcode] = r;
      return json(results);
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

    // The frame's note is shown.
    expect(within(scannedTable()).getByText("Box 3, iron oxides")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "mark as received AAAA-AAAA" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "move to external storage AAAA-AAAA" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "mark as returning to user AAAA-AAAA" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "void frame AAAA-AAAA" })).toBeEnabled();
    for (const label of [
      "mark as received",
      "move to external storage",
      "mark as returning to user",
      "void frame",
    ]) {
      expect(screen.getByRole("button", { name: `${label} BBBB-BBBB` })).toBeDisabled();
    }
  });

  it("keeps a moved frame in the table with its new status and the action taken", async () => {
    const fetchMock = mockScanApi();
    renderWithProviders(<ScanPage />);
    await scan("AAAA-AAAA");
    await scan("BBBB-BBBB");

    await userEvent.click(await screen.findByRole("button", { name: "mark as received AAAA-AAAA" }));

    const row = await waitFor(() => {
      const r = within(scannedTable()).getByText("AAAA-AAAA").closest("tr")!;
      expect(r).toHaveTextContent("Received");
      return r;
    });
    expect(row).toHaveTextContent("mark as received"); // last action
    // The untouched row has no last action.
    expect(within(scannedTable()).getByText("BBBB-BBBB").closest("tr")).not.toHaveTextContent(
      "mark as received",
    );

    const apply = fetchMock.mock.calls.map(([r]) => r).find((r) => r.url.endsWith("/scans/apply"))!;
    expect(await apply.json()).toEqual({ action: "receive", barcodes: ["AAAA-AAAA"] });
  });

  it("asks before voiding a frame", async () => {
    const fetchMock = mockScanApi();
    renderWithProviders(<ScanPage />);
    await scan("AAAA-AAAA");

    await userEvent.click(await screen.findByRole("button", { name: "void frame AAAA-AAAA" }));
    const dialog = await screen.findByRole("dialog", { name: "Void frame" });
    expect(fetchMock.mock.calls.some(([r]) => r.url.endsWith("/scans/apply"))).toBe(false);

    await userEvent.click(within(dialog).getByRole("button", { name: "Void" }));
    await waitFor(() =>
      expect(within(scannedTable()).getByText("AAAA-AAAA").closest("tr")).toHaveTextContent(
        "void frame",
      ),
    );
    expect(within(scannedTable()).getByText("Void")).toBeInTheDocument(); // new status
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
