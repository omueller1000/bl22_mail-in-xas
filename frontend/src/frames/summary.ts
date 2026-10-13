import type { Frame, PlateType } from "../api/client";

/** "8-Circle | 8-Slot", "8-Circle | empty", "6-Circle-Gas" (whole frame) or "—". */
export function plateSummary(frame: Pick<Frame, "plates">, plateTypes: PlateType[]): string {
  const left = plateTypes.find((t) => t.id === frame.plates.left);
  const right = plateTypes.find((t) => t.id === frame.plates.right);
  if (!left && !right) return "—";
  if (left?.blocks_other_side) return left.name;
  return `${left?.name ?? "empty"} | ${right?.name ?? "empty"}`;
}
