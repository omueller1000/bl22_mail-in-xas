import {
  ActionIcon,
  Button,
  Card,
  Grid,
  Group,
  SegmentedControl,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconArrowRight, IconCheck, IconX } from "@tabler/icons-react";
import { useState } from "react";

import type { ScanAction, ScanResult } from "../../api/client";
import { checkScan, useApplyScan } from "../../api/scanning";
import { ScanInput } from "../../components/ScanInput";
import { FRAME_STATE_LABELS, frameStateColor } from "../../materials/labels";
import { FrameStateBadge } from "../../frames/FrameStateBadge";

const ACTIONS: { value: ScanAction; label: string; button: string }[] = [
  { value: "receive", label: "Receive", button: "Receive" },
  { value: "external_storage", label: "External storage", button: "Move to external storage" },
  { value: "return", label: "Return to user", button: "Mark returned" },
  { value: "void", label: "Void", button: "Void" },
];

/**
 * Group scanning (requirements §9.1): scanned codes collect in the left table with what the
 * action would do; the action moves every frame that can make the move into the right table.
 * Frames that cannot move stay on the left, highlighted with the reason.
 */
export function ScanPage() {
  const [action, setAction] = useState<ScanAction>("receive");
  const [scanned, setScanned] = useState<ScanResult[]>([]);
  const [done, setDone] = useState<ScanResult[]>([]);
  const [checking, setChecking] = useState(false);
  const apply = useApplyScan();
  const current = ACTIONS.find((a) => a.value === action)!;
  const movable = scanned.filter((r) => r.target_state);

  const recheck = async (nextAction: ScanAction, codes: string[]) => {
    if (codes.length === 0) return setScanned([]);
    setChecking(true);
    try {
      setScanned(await checkScan(nextAction, codes));
    } catch (err) {
      notifications.show({ color: "red", message: (err as Error).message });
    } finally {
      setChecking(false);
    }
  };

  const onScan = (barcode: string) => {
    if (scanned.some((r) => r.barcode === barcode)) {
      notifications.show({ color: "yellow", message: `${barcode} is already in the list` });
      return;
    }
    void recheck(action, [...scanned.map((r) => r.barcode), barcode]);
  };

  const changeAction = (value: string) => {
    setAction(value as ScanAction);
    setDone([]);
    void recheck(value as ScanAction, scanned.map((r) => r.barcode));
  };

  const run = () =>
    apply.mutate(
      { action, barcodes: movable.map((r) => r.barcode) },
      {
        onSuccess: (results) => {
          const moved = results.filter((r) => r.moved);
          const movedCodes = new Set(moved.map((r) => r.barcode));
          setDone((rows) => [...moved, ...rows]);
          // Frames that did not move (e.g. changed meanwhile) stay with a fresh check.
          void recheck(action, scanned.map((r) => r.barcode).filter((c) => !movedCodes.has(c)));
          notifications.show({ color: "green", message: `${moved.length} frame(s) done` });
        },
        onError: (err) => notifications.show({ color: "red", message: err.message }),
      },
    );

  return (
    <Stack>
      <Title order={2}>Scan frames</Title>
      <SegmentedControl data={ACTIONS} value={action} onChange={changeAction} w="fit-content" />
      <Grid gap="lg">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card withBorder>
            <Stack>
              <Group justify="space-between" align="flex-end">
                <ScanInput onScan={onScan} disabled={apply.isPending} />
                <Group gap="xs">
                  <Button
                    variant="default"
                    disabled={scanned.length === 0}
                    onClick={() => setScanned([])}
                  >
                    Clear
                  </Button>
                  <Button
                    rightSection={<IconArrowRight size={16} />}
                    disabled={movable.length === 0 || checking}
                    loading={apply.isPending}
                    onClick={run}
                  >
                    {current.button} ({movable.length})
                  </Button>
                </Group>
              </Group>
              <ScannedTable
                rows={scanned}
                onRemove={(code) => setScanned((rows) => rows.filter((r) => r.barcode !== code))}
              />
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card withBorder>
            <Text fw={600} mb="xs">
              Done ({done.length})
            </Text>
            <DoneTable rows={done} />
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}

function ScannedTable({ rows, onRemove }: { rows: ScanResult[]; onRemove: (code: string) => void }) {
  if (rows.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        Scan frame barcodes; they collect here.
      </Text>
    );
  }
  return (
    <Table.ScrollContainer minWidth={560}>
      <Table aria-label="Scanned frames">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Barcode</Table.Th>
            <Table.Th>User</Table.Th>
            <Table.Th>Now</Table.Th>
            <Table.Th>Safe</Table.Th>
            <Table.Th>Locked</Table.Th>
            <Table.Th>Result</Table.Th>
            <Table.Th w={30} />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r) => (
            <Table.Tr
              key={r.barcode}
              bg={r.problem ? "var(--mantine-color-red-light)" : r.warning ? "var(--mantine-color-yellow-light)" : undefined}
            >
              <Table.Td ff="monospace">{r.barcode}</Table.Td>
              <Table.Td>{r.owner ?? "—"}</Table.Td>
              <Table.Td>{r.current_state ? <FrameStateBadge state={r.current_state} /> : "—"}</Table.Td>
              <Table.Td>{flag(r.current_state ? r.safe : null)}</Table.Td>
              <Table.Td>{flag(r.current_state ? r.locked : null)}</Table.Td>
              <Table.Td>
                {r.target_state ? (
                  <Stack gap={0}>
                    <Text size="sm" c={frameStateColor(r.target_state)}>
                      → {FRAME_STATE_LABELS[r.target_state]}
                    </Text>
                    {r.warning && (
                      <Text size="xs" c="var(--mantine-color-yellow-light-color)" fw={600}>
                        {r.warning}
                      </Text>
                    )}
                  </Stack>
                ) : (
                  <Text size="sm" c="red" fw={500}>
                    {r.problem}
                  </Text>
                )}
              </Table.Td>
              <Table.Td>
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  size="sm"
                  aria-label={`Remove ${r.barcode}`}
                  onClick={() => onRemove(r.barcode)}
                >
                  <IconX size={14} />
                </ActionIcon>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

function DoneTable({ rows }: { rows: ScanResult[] }) {
  if (rows.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        Frames the action has moved appear here.
      </Text>
    );
  }
  return (
    <Table aria-label="Done">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Barcode</Table.Th>
          <Table.Th>User</Table.Th>
          <Table.Th>New state</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {rows.map((r) => (
          <Table.Tr key={r.barcode}>
            <Table.Td ff="monospace">{r.barcode}</Table.Td>
            <Table.Td>{r.owner ?? "—"}</Table.Td>
            <Table.Td>
              {r.target_state && (
                <FrameStateBadge
                  state={r.target_state}
                  color={frameStateColor(r.target_state) ?? (r.warning ? "yellow" : "green")}
                />
              )}
              {r.warning && (
                <Text size="xs" c="dimmed">
                  {r.warning}
                </Text>
              )}
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

function flag(value: boolean | null) {
  if (value === null) return "—";
  return value ? (
    <IconCheck size={16} color="var(--mantine-color-green-6)" aria-label="yes" />
  ) : (
    <IconX size={16} color="var(--mantine-color-red-6)" aria-label="no" />
  );
}
