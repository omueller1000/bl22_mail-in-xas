import { Alert, Button, Card, Group, NumberInput, Stack, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { useBeamline, useRestoreBeamline, useSetBeamline } from "../../api/beamline";
import type { components } from "../../api/schema";
import { PageLoader } from "../../auth/guards";

type BeamlineSettings = components["schemas"]["BeamlineSettings"];

const keV = (ev: number) => ev / 1000;

/** The beamline's energy range, which limits the elements and edges users can choose. */
export function BeamlinePage() {
  const { data: settings, isPending, error } = useBeamline();

  return (
    <Stack>
      <Title order={2}>Beamline</Title>
      <Text c="dimmed" size="sm">
        Users can only choose element edges whose energy lies within this range. Changes apply to
        new and changed measurements immediately; existing measurements keep their edge.
      </Text>
      {isPending ? (
        <PageLoader />
      ) : error ? (
        <Alert color="red">{error.message}</Alert>
      ) : (
        // Re-mount the form when the saved values change, so it starts from them.
        <EnergyRangeCard key={`${settings.energy_min}-${settings.energy_max}`} settings={settings} />
      )}
    </Stack>
  );
}

function EnergyRangeCard({ settings }: { settings: BeamlineSettings }) {
  const save = useSetBeamline();
  const restore = useRestoreBeamline();
  const [min, setMin] = useState<number | string>(keV(settings.energy_min));
  const [max, setMax] = useState<number | string>(keV(settings.energy_max));

  const valid = typeof min === "number" && typeof max === "number" && min < max;
  const edited = min !== keV(settings.energy_min) || max !== keV(settings.energy_max);
  const isDefault =
    settings.energy_min === settings.default_min && settings.energy_max === settings.default_max;
  const fail = (e: Error) => notifications.show({ color: "red", message: e.message });

  return (
    <Card withBorder maw={560}>
      <Stack>
        <Text fw={600}>Energy range</Text>
        <Group align="flex-start">
          <NumberInput
            label="Minimum"
            suffix=" keV"
            decimalScale={3}
            min={0.1}
            max={200}
            value={min}
            onChange={setMin}
            w={150}
          />
          <NumberInput
            label="Maximum"
            suffix=" keV"
            decimalScale={3}
            min={0.1}
            max={200}
            value={max}
            onChange={setMax}
            w={150}
            error={typeof min === "number" && typeof max === "number" && min >= max ? "Must be above the minimum" : undefined}
          />
        </Group>
        <Text size="sm">
          {settings.edges_available} of {settings.edges_total} edges (Ti to Bi, K and L1–L3) are
          within the current range. Default: {keV(settings.default_min)}–{keV(settings.default_max)}{" "}
          keV.
        </Text>
        <Group justify="space-between">
          <Button
            variant="default"
            disabled={isDefault}
            loading={restore.isPending}
            onClick={() => restore.mutate(undefined, { onError: fail })}
          >
            Restore defaults
          </Button>
          <Button
            disabled={!edited || !valid}
            loading={save.isPending}
            onClick={() =>
              save.mutate(
                { energy_min: Number(min) * 1000, energy_max: Number(max) * 1000 },
                {
                  onSuccess: () =>
                    notifications.show({ color: "green", message: "Energy range applied" }),
                  onError: fail,
                },
              )
            }
          >
            Apply
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
