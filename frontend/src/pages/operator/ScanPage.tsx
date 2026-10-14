import {
  ActionIcon,
  Button,
  Card,
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

import type { ActionOutcome, ScanAction, ScannedFrame } from "../../api/client";
import { lookupScan, useApplyScan } from "../../api/scanning";
import { ScanInput } from "../../components/ScanInput";
import { FrameStateBadge } from "../../frames/FrameStateBadge";

const ACTIONS: { action: ScanAction; label: string; icon: ReactNode; color: string }[] = [
  {
    action: "receive",
    label: "mark as received",
    icon: <IconPackageImport size={18} />,
    color: "blue"
  },
  {
    action: "external_storage",
    label: "move to external storage",
    icon: <IconBuildingWarehouse size={18} />,
    color: "teal",
  },
  {
    action: "return",
    label: "mark as returned to user",
    icon: <IconTruckReturn size={18} />,
    color: "grape"
  },
  {
    action: "void",
    label: "void frame",
    icon: <IconBan size={18} />,
    color: "red"
  },
];

/**
 * Scanning at the facility (requirements §9): scanned frames collect in one table, each with one
 * button per action. A button is enabled only if that move is possible. After an action the row
 * stays, shows the frame's new status and the action taken, and is marked as handled.
 */
export function ScanPage() {
  const [scanned, setScanned] = useState<ScannedFrame[]>([]);
  // Barcode -> label of the last action taken on it in this session.
  const [lastAction, setLastAction] = useState<Record<string, string>>({});
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
            setLastAction((last) => ({ ...last, [barcode]: label }));
            notifications.show({ color: "green", message: `${barcode}: ${label}` });
          } else {
            fail(new Error(`${barcode}: ${result?.problem ?? "could not be moved"}`));
          }
          // Refresh the rows: new status and the actions now possible.
          void lookup(scanned.map((f) => f.barcode));
        },
        onError: fail,
      },
    );

  const remove = (barcode: string) => {
    setScanned((rows) => rows.filter((f) => f.barcode !== barcode));
    setLastAction((last) => {
      const next = { ...last };
      delete next[barcode];
      return next;
    });
  };

  return (
    <Stack>
      <Title order={2}>Scan frames</Title>
      <Card withBorder>
        <Stack>
          <Group justify="space-between" align="flex-end">
            <ScanInput onScan={onScan} disabled={apply.isPending} />
            <Button
              variant="default"
              disabled={scanned.length === 0}
              onClick={() => {
                setScanned([]);
                setLastAction({});
              }}
            >
              Clear
            </Button>
          </Group>
          <ScannedTable
            rows={scanned}
            lastAction={lastAction}
            busy={apply.isPending}
            onAction={(barcode, action) =>
              action === "void" ? setConfirmVoid(barcode) : run(barcode, action)
            }
            onRemove={remove}
          />
        </Stack>
      </Card>
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
  lastAction,
  busy,
  onAction,
  onRemove,
}: {
  rows: ScannedFrame[];
  lastAction: Record<string, string>;
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
    <Table.ScrollContainer minWidth={760}>
      <Table aria-label="Scanned frames">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Barcode</Table.Th>
            <Table.Th>User</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Safe</Table.Th>
            <Table.Th>Locked</Table.Th>
            <Table.Th>Action</Table.Th>
            <Table.Th>Last action</Table.Th>
            <Table.Th w={30} />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((f) => (
            <Table.Tr
              key={f.barcode}
              bg={
                !f.current_state
                  ? "var(--mantine-color-red-light)"
                  : lastAction[f.barcode]
                    ? "var(--mantine-color-green-light)"
                    : undefined
              }
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
                <Text size="sm">{lastAction[f.barcode] ?? ""}</Text>
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

/** The action's name (plus a warning if any), or "<name>: <reason>" when not possible. */
function hint(label: string, o: ActionOutcome): string {
  if (!o.target_state) return `${label}: ${o.problem ?? "not possible"}`;
  return `${label}${o.warning ? `. ${o.warning}` : ""}`;
}

function flag(value: boolean | null) {
  if (value === null) return "—";
  return value ? (
    <IconCheck size={16} color="var(--mantine-color-green-6)" aria-label="yes" />
  ) : (
    <IconX size={16} color="var(--mantine-color-red-6)" aria-label="no" />
  );
}
