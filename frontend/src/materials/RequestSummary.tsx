import { Text } from "@mantine/core";

import type { MaterialRequest } from "../api/client";
import { usePlateTypes } from "../api/materials";

/** "4× 8-Circle, 2× 6-Circle-Gas" (or "no plates"). */
export function PlateList({ request }: { request: Pick<MaterialRequest, "plates"> }) {
  const { data: types } = usePlateTypes();
  if (request.plates.length === 0) return <Text c="dimmed">no plates</Text>;
  const name = (id: string) => types?.find((t) => t.id === id)?.name ?? id;
  return <Text>{request.plates.map((p) => `${p.quantity}× ${name(p.plate_type)}`).join(", ")}</Text>;
}
