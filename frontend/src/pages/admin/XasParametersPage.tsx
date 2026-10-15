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
import { Fragment, useState } from "react";

import type { XasParameter } from "../../api/client";
import {
  useRestoreXasParameters,
  useSetXasParameters,
  useXasParameters,
} from "../../api/xasParameters";
import { PageLoader } from "../../auth/guards";

type Values = Record<string, number | null>;

const valuesOf = (params: XasParameter[]): Values =>
  Object.fromEntries(params.map((p) => [p.name, p.value]));

/** Change the parameters of the XAS processing (requirements §11.2). Admin only. */
export function XasParametersPage() {
  const { data: params, isPending, error } = useXasParameters();

  return (
    <Stack>
      <Title order={2}>XAS parameters</Title>
      <Text c="dimmed" size="sm">
        Parameters of the XAS data processing (normalisation, background, χ(k) and Fourier
        transform). Changes apply to all users immediately, in the data viewer and in exports.
      </Text>
      {isPending ? (
        <PageLoader />
      ) : error ? (
        <Alert color="red">{error.message}</Alert>
      ) : (
        // Re-mount the form when the saved values change, so it starts from them.
        <ParametersForm key={JSON.stringify(valuesOf(params))} params={params} />
      )}
    </Stack>
  );
}

function ParametersForm({ params }: { params: XasParameter[] }) {
  const save = useSetXasParameters();
  const restore = useRestoreXasParameters();
  const [values, setValues] = useState<Values>(() => valuesOf(params));
  const [confirmRestore, setConfirmRestore] = useState(false);

  const saved = valuesOf(params);
  const edited = params.some((p) => values[p.name] !== saved[p.name]);
  const anyChanged = params.some((p) => p.value !== p.default);
  const missing = params.filter((p) => values[p.name] === null && !p.none_means);
  const groups = [...new Set(params.map((p) => p.group))];

  const fail = (e: Error) => notifications.show({ color: "red", message: e.message });

  return (
    <Stack>
      <Table.ScrollContainer minWidth={640}>
        <Table verticalSpacing={4} aria-label="XAS parameters">
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
            {groups.map((group) => (
              <Fragment key={group}>
                <Table.Tr bg="var(--mantine-color-default-hover)">
                  <Table.Td colSpan={5} fw={600}>
                    {group}
                  </Table.Td>
                </Table.Tr>
                {params
                  .filter((p) => p.group === group)
                  .map((p) => (
                    <ParameterRow
                      key={p.name}
                      param={p}
                      value={values[p.name] ?? null}
                      onChange={(value) => setValues({ ...values, [p.name]: value })}
                    />
                  ))}
              </Fragment>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Group justify="space-between">
        <Button
          variant="default"
          disabled={!anyChanged}
          onClick={() => setConfirmRestore(true)}
        >
          Restore defaults
        </Button>
        <Group>
          <Button variant="default" disabled={!edited} onClick={() => setValues(saved)}>
            Discard edits
          </Button>
          <Button
            disabled={!edited || missing.length > 0}
            loading={save.isPending}
            onClick={() =>
              save.mutate(values, {
                onSuccess: () =>
                  notifications.show({ color: "green", message: "Parameters applied" }),
                onError: fail,
              })
            }
          >
            Apply
          </Button>
        </Group>
      </Group>

      <Modal
        opened={confirmRestore}
        onClose={() => setConfirmRestore(false)}
        title="Restore the default parameters?"
      >
        <Stack>
          <Text size="sm">
            All parameters go back to their defaults. This applies to all users immediately.
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

function ParameterRow({
  param: p,
  value,
  onChange,
}: {
  param: XasParameter;
  value: number | null;
  onChange: (value: number | null) => void;
}) {
  const changed = p.value !== p.default;
  const missing = value === null && !p.none_means;
  return (
    <Table.Tr>
      <Table.Td>
        <Group gap={6} wrap="nowrap">
          <Text size="sm">{p.label}</Text>
          {changed && (
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
          placeholder={p.none_means ?? undefined}
          value={value ?? ""}
          onChange={(v) => onChange(v === "" ? null : Number(v))}
          min={p.minimum}
          max={p.maximum}
          step={p.integer ? 1 : 0.1}
          allowDecimal={!p.integer}
          clampBehavior="strict"
          error={missing ? "Required" : undefined}
        />
      </Table.Td>
      <Table.Td>
        <Text size="sm" c="dimmed">
          {p.unit}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm" c="dimmed">
          {p.default === null ? p.none_means : p.default}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm" c="dimmed">
          {p.minimum}–{p.maximum}
          {p.none_means && `, or empty (${p.none_means})`}
        </Text>
      </Table.Td>
    </Table.Tr>
  );
}
