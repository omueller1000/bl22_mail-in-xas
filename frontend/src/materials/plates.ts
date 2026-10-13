import circle6Gas from "../assets/plates/6-circle-gas.png";
import circle8 from "../assets/plates/8-circle.png";
import slot8 from "../assets/plates/8-slot.png";
import type { PlateType } from "../api/client";

/** Drawings of the plate types (from v1), keyed by catalog id. */
export const PLATE_IMAGES: Record<string, string> = {
  "8-circle": circle8,
  "8-slot": slot8,
  "6-circle-gas": circle6Gas,
};

export const MAX_FRAMES_PER_REQUEST = 100;

/**
 * Allowed number of frames for the requested plates (mirrors the backend, requirements §7):
 * plates that block the other side need a frame each, the others fit two per frame.
 */
export function frameRange(
  plateTypes: PlateType[],
  quantities: Record<string, number>,
): [number, number] {
  let blocking = 0;
  let others = 0;
  for (const type of plateTypes) {
    const n = quantities[type.id] ?? 0;
    if (type.blocks_other_side) blocking += n;
    else others += n;
  }
  if (blocking + others === 0) return [1, MAX_FRAMES_PER_REQUEST];
  return [blocking + Math.ceil(others / 2), blocking + others];
}
