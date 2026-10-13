import { vi } from "vitest";

import type { Me, User } from "../api/client";

type Handler = (request: Request) => Response | Promise<Response>;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Replace fetch with a fake API. Keys are "METHOD /path" relative to the API base,
 * e.g. "GET /auth/me". Unknown routes answer 404. Returns the mock to inspect requests.
 */
export function mockApi(routes: Record<string, Handler>) {
  const apiBase = `${import.meta.env.BASE_URL}api`;
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>(async (request) => {
    const path = new URL(request.url).pathname.slice(apiBase.length);
    const handler = routes[`${request.method} ${path}`];
    return handler ? handler(request) : json({ detail: "Not Found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export const TEST_USER: User = {
  id: "u1",
  orcid: "0000-0002-1825-0097",
  name: "Ada Test",
  role: "user",
  email: "ada@example.org",
  phone: "+1 650 555 0100",
  affiliation: "Example University",
  shipping_address: {
    care_of: null,
    street1: "1 Example Way",
    street2: null,
    city: "Example City",
    region: "CA",
    postal_code: "94025",
    country: "USA",
  },
  created_at: "2026-10-12T00:00:00Z",
};

export function meResponse(overrides: Partial<Me>): Me {
  return {
    status: "anonymous",
    orcid_login_enabled: true,
    dev_login_enabled: false,
    orcid: null,
    orcid_name: null,
    user: null,
    ...overrides,
  };
}
