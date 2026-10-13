import type { Measurement, MeasurementOptions } from "../api/client";

/** "XANES · Fe K · Transmission + SDD · Focused" */
export function describeMeasurement(
  m: Pick<Measurement, "technique" | "element" | "edge" | "detection" | "beam">,
  options: MeasurementOptions | undefined,
): string {
  const label = (list: { value: string; label: string }[] | undefined, value: string) =>
    list?.find((o) => o.value === value)?.label ?? value;
  return [
    label(options?.techniques, m.technique),
    `${m.element} ${m.edge}`,
    label(options?.detections, m.detection),
    label(options?.beams, m.beam),
  ].join(" · ");
}

export const MEASUREMENT_STATUS: Record<Measurement["status"], { label: string; color: string }> = {
  pending: { label: "Pending", color: "gray" },
  done: { label: "Done", color: "green" },
  error: { label: "Error", color: "red" },
};
