import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ApiKey, ServiceClient } from "../../api/client";
import { json, mockApi } from "../../test/mockApi";
import { renderWithProviders } from "../../test/render";
import { ServiceClientsPage } from "./ServiceClientsPage";

const KEY: ApiKey = {
  id: "k1",
  prefix: "htxas_AbCdEf",
  created_at: "2026-10-14T08:00:00Z",
  created_by: "Ada Admin",
  last_used_at: null,
  revoked_at: null,
};

const CLIENT: ServiceClient = {
  id: "c1",
  name: "BL22 control software",
  created_at: "2026-10-14T08:00:00Z",
  created_by: "Ada Admin",
  keys: [KEY],
};

describe("ServiceClientsPage", () => {
  it("shows a new key once", async () => {
    mockApi({
      "GET /service-clients": () => json([CLIENT]),
      "POST /service-clients/c1/keys": () =>
        json({ key: "htxas_AbCdEf_the_full_secret_key", info: { ...KEY, id: "k2" } }, 201),
    });
    renderWithProviders(<ServiceClientsPage />);
    expect(await screen.findByText("htxas_AbCdEf…")).toBeInTheDocument();
    expect(screen.getByText("never")).toBeInTheDocument(); // last used

    await userEvent.click(screen.getByRole("button", { name: "New key" }));
    const dialog = await screen.findByRole("dialog", { name: "New API key" });
    expect(within(dialog).getByText("htxas_AbCdEf_the_full_secret_key")).toBeInTheDocument();
    expect(within(dialog).getByText(/will not be shown again/)).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("button", { name: "Done" }));
    await waitFor(() =>
      expect(screen.queryByText("htxas_AbCdEf_the_full_secret_key")).not.toBeInTheDocument(),
    );
  });

  it("revokes a key after confirmation", async () => {
    const fetchMock = mockApi({
      "GET /service-clients": () => json([CLIENT]),
      "DELETE /service-clients/c1/keys/k1": () =>
        json({ ...KEY, revoked_at: "2026-10-14T09:00:00Z" }),
    });
    renderWithProviders(<ServiceClientsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Revoke key htxas_AbCdEf" }));
    const dialog = await screen.findByRole("dialog", { name: "Revoke API key" });
    expect(fetchMock.mock.calls.some(([r]) => r.method === "DELETE")).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: "Revoke" }));

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([r]) => r.method === "DELETE")).toBe(true),
    );
  });
});
