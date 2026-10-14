import {
  ActionIcon,
  Button,
  Card,
  Grid,
  Group,
  Modal,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconBan,
  IconBuildingWarehouse,
  IconCheck,
  IconPackageImport,
  IconTruckReturn,
  IconX,
} from "@tabler/icons-react";
import { type ReactNode, useState } from "react";

import type { ActionOutcome, ScanAction, ScannedFrame, ScanResult } from "../../api/client";
import { lookupScan, useApplyScan } from "../../api/scanning";
import { ScanInput } from "../../components/ScanInput";
import { FrameStateBadge } from "../../frames/FrameStateBadge";
import { FRAME_STATE_LABELS, frameStateColor } from "../../materials/labels";

const ACTIONS: { action: ScanAction; label: string; icon: ReactNode; color: string }[] = [
  { action: "receive", label: "Receive", icon: <IconPackageImport size={18} />, color: "blue" },
  {
    action: "external_storage",
    label: "External storage",
    icon: <IconBuildingWarehouse size={18} />,
    color: "teal",
  },
  { action: "return", label: "Return to user", icon: <IconTruckReturn size={18} />, color: "grape" },
  { action: "void", label: "Void", icon: <IconBan size={18} />, color: "red" },
];

interface Done extends ScanResult {
  label: string;
}

/**
 * Scanning at the facility (requirements §9): scanned frames collect in the left table, each
 * with one button per action. A button is enabled only if that move is possible; its tooltip
 * says what will happen. Moved frames go to the right table.
 */
export function ScanPage() {
  const [scanned, setScanned] = useState<ScannedFrame[]>([]);
  const [done, setDone] = useState<Done[]>([]);
  const [confirmVoid, setConfirmVoid] = useState<string | null>(null);
  const apply = useApplyScan();
  const fail = (err: Error) => notifications.show({ color: "red", message: err.message });

  const lookup = async (codes: string[]) => {
    if (codes.length === 0) return setScanned([]);
    try {
      setScanned(await lookupScan(codes));
    } catch (err) {
      fail(err as Error);
    }
  };

  const onScan = (barcode: string) => {
    if (scanned.some((f) => f.barcode === barcode)) {
      notifications.show({ color: "yellow", message: `${barcode} is already in the list` });
      return;
    }
    void lookup([...scanned.map((f) => f.barcode), barcode]);
  };

  const run = (barcode: string, action: ScanAction) =>
    apply.mutate(
      { action, barcodes: [barcode] },
      {
        onSuccess: ([result]) => {
          const label = ACTIONS.find((a) => a.action === action)!.label;
          if (result?.moved) {
            setDone((rows) => [{ ...result, label }, ...rows]);
            setScanned((rows) => rows.filter((f) => f.barcode !== barcode));
          } else {
            fail(new Error(`${barcode}: ${result?.problem ?? "could not be moved"}`));
            void lookup(scanned.map((f) => f.barcode)); // the frame changed meanwhile
          }
        },
        onError: fail,
      },
    );

  return (
    <Stack>
      <Title order={2}>Scan frames</Title>
      <Grid gap="lg">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card withBorder>
            <Stack>
              <Group justify="space-between" align="flex-end">
                <ScanInput onScan={onScan} disabled={apply.isPending} />
                <Button
                  variant="default"
                  disabled={scanned.length === 0}
                  onClick={() => setScanned([])}
                >
                  Clear
                </Button>
              </Group>
              <ScannedTable
                rows={scanned}
                busy={apply.isPending}
                onAction={(barcode, action) =>
                  action === "void" ? setConfirmVoid(barcode) : run(barcode, action)
                }
                onRemove={(code) => setScanned((rows) => rows.filter((f) => f.barcode !== code))}
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
      <Modal opened={confirmVoid !== null} onClose={() => setConfirmVoid(null)} title="Void frame">
        <Stack>
          <Text size="sm">
            Void <b>{confirmVoid}</b>? A voided frame (lost or damaged) can no longer be used. This
            cannot be undone.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirmVoid(null)}>
              Cancel
            </Button>
            <Button
              color="red"
              loading={apply.isPending}
              onClick={() => {
                if (confirmVoid) run(confirmVoid, "void");
                setConfirmVoid(null);
              }}
            >
              Void
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

function ScannedTable({
  rows,
  busy,
  onAction,
  onRemove,
}: {
  rows: ScannedFrame[];
  busy: boolean;
  onAction: (barcode: string, action: ScanAction) => void;
  onRemove: (barcode: string) => void;
}) {
  if (rows.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        Scan frame barcodes; they collect here.
      </Text>
    );
  }
  return (
    <Table.ScrollContainer minWidth={640}>
      <Table aria-label="Scanned frames">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Barcode</Table.Th>
            <Table.Th>User</Table.Th>
            <Table.Th>Now</Table.Th>
            <Table.Th>Safe</Table.Th>
            <Table.Th>Locked</Table.Th>
            <Table.Th>Action</Table.Th>
            <Table.Th w={30} />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((f) => (
            <Table.Tr
              key={f.barcode}
              bg={f.current_state ? undefined : "var(--mantine-color-red-light)"}
            >
              <Table.Td ff="monospace">{f.barcode}</Table.Td>
              <Table.Td>{f.owner ?? "—"}</Table.Td>
              <Table.Td>
                {f.current_state ? (
                  <FrameStateBadge state={f.current_state} />
                ) : (
                  <Text size="sm" c="red" fw={500}>
                    Unknown barcode
                  </Text>
                )}
              </Table.Td>
              <Table.Td>{flag(f.current_state ? f.safe : null)}</Table.Td>
              <Table.Td>{flag(f.current_state ? f.locked : null)}</Table.Td>
              <Table.Td>
                <Group gap={4} wrap="nowrap">
                  {ACTIONS.map((a) => {
                    const o = f.actions.find((x) => x.action === a.action)!;
                    return (
                      <Tooltip key={a.action} label={hint(a.label, o)} withArrow multiline maw={260}>
                        <ActionIcon
                          variant="light"
                          color={a.color}
                          aria-label={`${a.label} ${f.barcode}`}
                          disabled={!o.target_state || busy}
                          onClick={() => onAction(f.barcode, a.action)}
                        >
                          {a.icon}
                        </ActionIcon>
                      </Tooltip>
                    );
                  })}
                </Group>
              </Table.Td>
              <Table.Td>
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  size="sm"
                  aria-label={`Remove ${f.barcode}`}
                  onClick={() => onRemove(f.barcode)}
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

/** "Receive → Received, on hold. Not declared safe: put on hold" or "Receive: <reason>". */
function hint(label: string, o: ActionOutcome): string {
  if (!o.target_state) return `${label}: ${o.problem ?? "not possible"}`;
  return `${label} → ${FRAME_STATE_LABELS[o.target_state]}${o.warning ? `. ${o.warning}` : ""}`;
}

function DoneTable({ rows }: { rows: Done[] }) {
  if (rows.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        Frames you move appear here.
      </Text>
    );
  }
  return (
    <Table aria-label="Done">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Barcode</Table.Th>
          <Table.Th>User</Table.Th>
          <Table.Th>Action</Table.Th>
          <Table.Th>New state</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {rows.map((r, i) => (
          <Table.Tr key={`${r.barcode}-${i}`}>
            <Table.Td ff="monospace">{r.barcode}</Table.Td>
            <Table.Td>{r.owner ?? "—"}</Table.Td>
            <Table.Td>{r.label}</Table.Td>
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
