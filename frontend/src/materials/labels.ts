import type { FrameState, RequestState } from "../api/client";

/*
 * Colour convention for the whole portal:
 *   red     blocked, needs action, or final (on hold, errors, void, delete)
 *   yellow  warning, attention needed (not locked, missing items, already executed)
 *   blue    normal state (the theme's default colour)
 *   indigo  in progress (being prepared, placed on this frame, at the beamline)
 *   green   done, success (fulfilled, measurement done, handled scan rows)
 *   orange  selection, or an emergency override (selected position or slot, release)
 */
export const IN_PROGRESS_COLOR = "indigo";

export type Audience = "user" | "operator";

/** Request states as shown to users and to operators (requirements §7). */
export const REQUEST_STATE: Record<
  RequestState,
  { color: string } & Record<Audience, string>
> = {
  submitted: { user: "Submitted", operator: "Open", color: "blue" },
  issued: { user: "Being prepared", operator: "Issued (to be shipped)", color: IN_PROGRESS_COLOR },
  fulfilled: { user: "Shipped", operator: "Fulfilled", color: "green" },
  rejected: { user: "Rejected", operator: "Rejected", color: "red" },
};

export const FRAME_STATE_LABELS: Record<FrameState, string> = {
  reserved: "Reserved",
  issued: "Issued",
  shipped_to_user: "Shipped to user",
  received: "Received",
  received_on_hold: "Received, on hold",
  external_storage: "External storage",
  internal_storage: "Internal storage",
  scheduled: "Scheduled",
  loaded: "Loaded",
  returned: "Returned",
  void: "Void",
};

/** Badge colour of a frame state; undefined = the theme's default colour. */
export function frameStateColor(state: FrameState): string | undefined {
  return state === "received_on_hold" ? "red" : undefined;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
