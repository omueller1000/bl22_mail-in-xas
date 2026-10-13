import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ScanResult } from "../../api/client";
import { json, mockApi } from "../../test/mockApi";
import { renderWithProviders } from "../../test/render";
import { ScanPage } from "./ScanPage";

/** Fake rules: AAAA-AAAA can be received (not locked), BBBB-BBBB cannot. */
function result(barcode: string, action: string, moved = false): ScanResult {
  const ok = barcode === "AAAA-AAAA";
  return {
    barcode,
    current_state: ok ? "shipped_to_user" : "issued",
    owner: "Ada Test",
    safe: ok,
    locked: false,
    target_state: ok ? (action === "receive" ? "received" : "returned") : null,
    problem: ok ? null : "Not possible from state issued",
    warning: ok && action === "receive" ? "Not locked" : null,
    moved,
  };
}

async function scan(code: string) {
  await userEvent.type(screen.getByRole("textbox", { name: "Scan barcode" }), `${code}{Enter}`);
}

describe("ScanPage", () => {
  it("moves frames that can make the move and keeps the others with the reason", async () => {
    const fetchMock = mockApi({
      "POST /scans/check": async (request) => {
        const body = (await request.clone().json()) as { action: string; barcodes: string[] };
        return json(body.barcodes.map((code) => result(code, body.action)));
      },
      "POST /scans/apply": async (request) => {
        const body = (await request.clone().json()) as { action: string; barcodes: string[] };
        return json(body.barcodes.map((code) => result(code, body.action, true)));
      },
    });
    renderWithProviders(<ScanPage />);

    await scan("AAAA-AAAA");
    await scan("BBBB-BBBB");
    const scanned = await screen.findByRole("table", { name: "Scanned frames" });
    expect(await within(scanned).findByText("Not possible from state issued")).toBeInTheDocument();
    expect(within(scanned).getByText("→ Received")).toBeInTheDocument();
    expect(within(scanned).getByText("Not locked")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Receive \(1\)/ }));

    const done = await screen.findByRole("table", { name: "Done" });
    expect(within(done).getByText("AAAA-AAAA")).toBeInTheDocument();
    await waitFor(() =>
      expect(within(screen.getByRole("table", { name: "Scanned frames" })).queryByText("AAAA-AAAA")).not.toBeInTheDocument(),
    );
    expect(within(screen.getByRole("table", { name: "Scanned frames" })).getByText("BBBB-BBBB")).toBeInTheDocument();

    const apply = fetchMock.mock.calls.map(([r]) => r).find((r) => r.url.endsWith("/scans/apply"))!;
    expect(await apply.json()).toEqual({ action: "receive", barcodes: ["AAAA-AAAA"] });
  });

  it("re-checks the scanned frames when the action changes", async () => {
    mockApi({
      "POST /scans/check": async (request) => {
        const body = (await request.clone().json()) as { action: string; barcodes: string[] };
        return json(body.barcodes.map((code) => result(code, body.action)));
      },
    });
    renderWithProviders(<ScanPage />);
    await scan("AAAA-AAAA");
    expect(await screen.findByText("→ Received")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Return to user"));
    expect(await screen.findByText("→ Returned")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Mark returned \(1\)/ })).toBeEnabled();
  });
});
