import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

type Schemas = components["schemas"];
export type HealthResponse = Schemas["HealthResponse"];
export type Me = Schemas["Me"];
export type User = Schemas["User"];
export type Profile = Schemas["Profile"];
export type Registration = Schemas["Registration"];
export type Address = Schemas["Address"];
export type Role = Schemas["Role"];
export type PlateType = Schemas["PlateType"];
export type Frame = Schemas["Frame"];
export type FrameState = Schemas["FrameState"];
export type ShippingGroup = Schemas["ShippingGroup"];
export type MaterialRequest = Schemas["MaterialRequest"];
export type MaterialRequestCreate = Schemas["MaterialRequestCreate"];
export type RequestState = Schemas["RequestState"];
export type Sample = Schemas["Sample"];
export type PlacedSample = Schemas["PlacedSample"];
export type Measurement = Schemas["Measurement"];
export type MeasurementInput = Schemas["MeasurementInput"];
export type MeasurementOptions = Schemas["MeasurementOptions"];
export type ScanAction = Schemas["ScanAction"];
export type ScanResult = Schemas["ScanResult"];
export type ScannedFrame = Schemas["ScannedFrame"];
export type ActionOutcome = Schemas["ActionOutcome"];
export type StoredFrame = Schemas["StoredFrame"];
export type FrameWarning = Schemas["FrameWarning"];
export type ServiceClient = Schemas["ServiceClient"];
export type ApiKey = Schemas["ApiKey"];
export type SweepInfo = Schemas["SweepInfo"];
export type SweepDetail = Schemas["SweepDetail"];
export type PlotCurve = Schemas["PlotCurve"];
export type DataView = Schemas["View"];
export type ProcessedSpectrum = Schemas["ProcessedSpectrum"];
export type XasParameter = Schemas["XasParameter"];

/** Absolute API base, e.g. http://host/mail-in-xas/api (prod) or .../mail-in-xas/dev/api (dev). */
export const API_BASE_URL = new URL(`${import.meta.env.BASE_URL}api`, window.location.origin)
  .toString()
  .replace(/\/$/, "");

/** Typed API client; paths and payloads come from the backend's OpenAPI schema. */
export const api = createClient<paths>({
  baseUrl: API_BASE_URL,
  credentials: "same-origin",
  // Required by the backend on state-changing requests (protection against forged requests).
  headers: { "X-Requested-With": "ht-xas" },
  // Look up fetch at call time (not import time), so tests can replace it.
  fetch: (request) => globalThis.fetch(request),
});

/** An error response from the API, with the backend's message. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, detail: unknown) {
    super(describe(detail) ?? `Request failed (HTTP ${status})`);
    this.status = status;
  }
}

function describe(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  // FastAPI validation errors: [{ loc: [...], msg: "..." }, ...]
  if (Array.isArray(detail)) {
    return detail
      .map((item: { loc?: unknown[]; msg?: string }) =>
        [item.loc?.slice(1).join("."), item.msg].filter(Boolean).join(": "),
      )
      .join("; ");
  }
  return undefined;
}

/** Return the data of an openapi-fetch result, or throw an ApiError. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data !== undefined) return result.data;
  const detail = (result.error as { detail?: unknown } | undefined)?.detail;
  throw new ApiError(result.response.status, detail);
}
