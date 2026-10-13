import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type HealthResponse = components["schemas"]["HealthResponse"];

/** Absolute API base, e.g. http://host/mail-in-xas/api (prod) or .../mail-in-xas/dev/api (dev). */
export const API_BASE_URL = new URL(`${import.meta.env.BASE_URL}api`, window.location.origin)
  .toString()
  .replace(/\/$/, "");

/** Typed API client; paths and payloads come from the backend's OpenAPI schema. */
export const api = createClient<paths>({
  baseUrl: API_BASE_URL,
  credentials: "same-origin",
  // Look up fetch at call time (not import time), so tests can replace it.
  fetch: (request) => globalThis.fetch(request),
});
