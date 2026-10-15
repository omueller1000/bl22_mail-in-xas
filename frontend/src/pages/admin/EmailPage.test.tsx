import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { json, mockApi } from "../../test/mockApi";
import { renderWithProviders } from "../../test/render";
import { EmailPage } from "./EmailPage";

const STATUS = {
  switches: { enabled: true, redirect_to: null },
  environment: "local",
  configured: true,
  from_address: "noreply@example.org",
  dev_redirect: null,
};

const EMAIL = {
  id: "e1",
  kind: "returned",
  to: ["ada@example.org"],
  subject: "BL22 mail-in XAS: frame AAAA-AAAA returned",
  status: "not_sent",
  attempts: 0,
  error: "Not production and no HT_XAS_MAIL_DEV_REDIRECT set",
  created_at: "2026-10-14T10:00:00Z",
  send_after: "2026-10-14T10:00:00Z",
  sent_at: null,
  delivered_to: null,
  text: "Dear Ada,\n\nFrame AAAA-AAAA is on its way back to you.",
};

function setup() {
  let status = STATUS;
  const fetchMock = mockApi({
    "GET /admin/mail": () => json(status),
    "PUT /admin/mail": async (request) => {
      status = { ...status, switches: await request.clone().json() };
      return json(status);
    },
    "GET /admin/mail/outbox": () => json([EMAIL]),
    "POST /admin/mail/test": () => new Response(null, { status: 204 }),
  });
  renderWithProviders(<EmailPage />);
  return fetchMock;
}

describe("EmailPage", () => {
  it("explains that nothing reaches users outside production", async () => {
    setup();
    expect(await screen.findByText(/emails never reach their recipients/)).toBeInTheDocument();
    expect(await screen.findByText(EMAIL.subject)).toBeInTheDocument();
    expect(screen.getByText("not sent")).toBeInTheDocument();
  });

  it("switches notifications off and sets a redirect", async () => {
    const fetchMock = setup();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("switch", { name: /Send notification emails/ }));
    await user.type(
      screen.getByRole("textbox", { name: /Redirect all notifications/ }),
      "debug@example.org",
    );
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(async () => {
      const put = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "PUT")!;
      expect(await put.clone().json()).toEqual({ enabled: false, redirect_to: "debug@example.org" });
    });
    expect(await screen.findByText("Notification emails are switched off.")).toBeInTheDocument();
  });

  it("shows the text of a recorded email", async () => {
    setup();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Show email/ }));
    expect(await screen.findByText(/is on its way back to you/)).toBeInTheDocument();
  });
});
