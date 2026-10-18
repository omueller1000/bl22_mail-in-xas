import {
  Alert,
  Badge,
  Button,
  Group,
  Modal,
  NumberInput,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { useBeamline, useRestoreBeamline, useSetBeamline } from "../../api/beamline";
import type { components } from "../../api/schema";
import { PageLoader } from "../../auth/guards";

type BeamlineSettings = components["schemas"]["BeamlineSettings"];
type Values = { energy_min: number | null; energy_max: number | null };

// What the backend accepts at all (app/beamline.py), in keV.
const ALLOWED_MIN = 1;
const ALLOWED_MAX = 100;

const keV = (ev: number) => ev / 1000;

const PARAMETERS = [
  { name: "energy_min", label: "Minimum energy", defaultKey: "default_min" },
  { name: "energy_max", label: "Maximum energy", defaultKey: "default_max" },
] as const;

const valuesOf = (s: BeamlineSettings): Values => ({
  energy_min: keV(s.energy_min),
  energy_max: keV(s.energy_max),
});

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
        <BeamlineForm key={`${settings.energy_min}-${settings.energy_max}`} settings={settings} />
      )}
    </Stack>
  );
}

function BeamlineForm({ settings }: { settings: BeamlineSettings }) {
  const save = useSetBeamline();
  const restore = useRestoreBeamline();
  const [values, setValues] = useState<Values>(() => valuesOf(settings));
  const [confirmRestore, setConfirmRestore] = useState(false);

  const saved = valuesOf(settings);
  const edited = values.energy_min !== saved.energy_min || values.energy_max !== saved.energy_max;
  const isDefault =
    settings.energy_min === settings.default_min && settings.energy_max === settings.default_max;
  const { energy_min: min, energy_max: max } = values;
  const outOfOrder = min !== null && max !== null && min >= max;
  const valid = min !== null && max !== null && !outOfOrder;
  const fail = (e: Error) => notifications.show({ color: "red", message: e.message });

  return (
    <Stack maw={760}>
      <Table.ScrollContainer minWidth={600}>
        <Table verticalSpacing={4} aria-label="Beamline parameters">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Parameter</Table.Th>
              <Table.Th w={150}>Value</Table.Th>
              <Table.Th w={70}>Unit</Table.Th>
              <Table.Th>Default</Table.Th>
              <Table.Th>Allowed</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            <Table.Tr bg="var(--mantine-color-default-hover)">
              <Table.Td colSpan={5} fw={600}>
                Energy range
              </Table.Td>
            </Table.Tr>
            {PARAMETERS.map((p) => {
              const value = values[p.name];
              const defaultValue = keV(settings[p.defaultKey]);
              const error =
                value === null
                  ? "Required"
                  : p.name === "energy_max" && outOfOrder
                    ? "Must be above the minimum"
                    : undefined;
              return (
                <Table.Tr key={p.name}>
                  <Table.Td>
                    <Group gap={6} wrap="nowrap">
                      <Text size="sm">{p.label}</Text>
                      {saved[p.name] !== defaultValue && (
                        <Badge size="xs" variant="light" color="orange">
                          changed
                        </Badge>
                      )}
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <NumberInput
                      aria-label={p.label}
                      size="xs"
                      value={value ?? ""}
                      onChange={(v) =>
                        setValues({ ...values, [p.name]: v === "" ? null : Number(v) })
                      }
                      min={ALLOWED_MIN}
                      max={ALLOWED_MAX}
                      step={0.1}
                      decimalScale={3}
                      clampBehavior="strict"
                      error={error}
                    />
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      keV
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {defaultValue}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      {ALLOWED_MIN}–{ALLOWED_MAX}
                    </Text>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Group justify="space-between">
        <Button variant="default" disabled={isDefault} onClick={() => setConfirmRestore(true)}>
          Restore defaults
        </Button>
        <Group>
          <Button variant="default" disabled={!edited} onClick={() => setValues(saved)}>
            Discard edits
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
      </Group>

      <Modal
        opened={confirmRestore}
        onClose={() => setConfirmRestore(false)}
        title="Restore the default energy range?"
      >
        <Stack>
          <Text size="sm">
            The energy range goes back to {keV(settings.default_min)}–{keV(settings.default_max)}{" "}
            keV. This applies to all users immediately.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirmRestore(false)}>
              Cancel
            </Button>
            <Button
              color="red"
              loading={restore.isPending}
              onClick={() =>
                restore.mutate(undefined, {
                  onSuccess: () => setConfirmRestore(false),
                  onError: fail,
                })
              }
            >
              Restore defaults
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
