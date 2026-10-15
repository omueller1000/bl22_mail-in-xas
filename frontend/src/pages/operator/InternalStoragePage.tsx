import {
  ActionIcon,
  Alert,
  Anchor,
  Box,
  Button,
  Card,
  Group,
  Modal,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
  UnstyledButton,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconArrowBackUp, IconBuildingWarehouse, IconLock } from "@tabler/icons-react";
import { useState } from "react";
import { Link } from "react-router";

import type { Frame, StoredFrame } from "../../api/client";
import { fetchFrame } from "../../api/materials";
import {
  useApplyScan,
  useInternalStorage,
  useRelease,
  useStoreInternally,
} from "../../api/scanning";
import { PageLoader } from "../../auth/guards";
import { ScanInput } from "../../components/ScanInput";
import { YesNoIcon } from "../../components/YesNoIcon";
import { FRAME_STATE_LABELS, formatDateTime, IN_PROGRESS_COLOR } from "../../materials/labels";
import { FrameStateBadge } from "../../frames/FrameStateBadge";

const CONTAINERS = [0, 1, 2];
const SLOTS = [...Array(11).keys()]; // 0-10
const STORABLE_STATES = ["received", "external_storage"];

/** Internal storage (requirements §9.2, §9.4): one frame at a time into a free slot. */
export function InternalStoragePage() {
  const { data: stored = [], isPending, error } = useInternalStorage();
  const [frame, setFrame] = useState<Frame | null>(null);
  const [container, setContainer] = useState(0);
  const [slot, setSlot] = useState<number | null>(null);

  const occupant = (c: number, s: number) => stored.find((f) => f.container === c && f.slot === s);

  return (
    <Stack>
      <Title order={2}>Internal Storage</Title>
      <MoveCard
        frame={frame}
        setFrame={setFrame}
        container={container}
        setContainer={(c) => {
          setContainer(c);
          setSlot(null);
        }}
        slot={slot}
        setSlot={setSlot}
        occupant={occupant}
      />
      {isPending ? (
        <PageLoader />
      ) : error ? (
        <Alert color="red">{error.message}</Alert>
      ) : (
        <>
          <OccupancyGrid
            occupant={occupant}
            selected={frame ? { container, slot } : null}
            onPick={(c, s) => {
              setContainer(c);
              setSlot(s);
            }}
          />
          <StoredTable rows={stored} />
        </>
      )}
    </Stack>
  );
}

function MoveCard({
  frame,
  setFrame,
  container,
  setContainer,
  slot,
  setSlot,
  occupant,
}: {
  frame: Frame | null;
  setFrame: (f: Frame | null) => void;
  container: number;
  setContainer: (c: number) => void;
  slot: number | null;
  setSlot: (s: number | null) => void;
  occupant: (c: number, s: number) => StoredFrame | undefined;
}) {
  const store = useStoreInternally();
  const [lookupError, setLookupError] = useState<string | null>(null);
  const storable = frame && STORABLE_STATES.includes(frame.state);

  const onScan = async (barcode: string) => {
    setLookupError(null);
    setSlot(null);
    try {
      const found = await fetchFrame(barcode);
      setFrame(found);
      if (!found) setLookupError(`Unknown barcode ${barcode}`);
    } catch (err) {
      setFrame(null);
      setLookupError((err as Error).message);
    }
  };

  const save = () =>
    frame &&
    slot !== null &&
    store.mutate(
      { barcode: frame.barcode, container, slot },
      {
        onSuccess: () => {
          notifications.show({
            color: "green",
            message: `${frame.barcode} stored in container ${container}, slot ${slot}`,
          });
          setFrame(null);
          setSlot(null);
        },
        onError: (err) => notifications.show({ color: "red", message: err.message }),
      },
    );

  return (
    <Card withBorder maw={720}>
      <Stack>
        <Text fw={600}>Move a frame into internal storage</Text>
        <ScanInput onScan={(code) => void onScan(code)} label="Scan frame" />
        {lookupError && <Alert color="red">{lookupError}</Alert>}
        {frame && (
          <>
            <Group gap="xs">
              <Text ff="monospace" fw={700}>
                {frame.barcode}
              </Text>
              <Text>{frame.owner?.name}</Text>
              <FrameStateBadge state={frame.state} />
              {frame.locked && <IconLock size={16} aria-label="locked" />}
            </Group>
            {!storable ? (
              <Alert color="red">
                Only received frames or frames in external storage can go into internal storage.
              </Alert>
            ) : (
              <Group align="flex-end">
                <Stack gap={4}>
                  <Text size="sm" fw={500}>
                    Container
                  </Text>
                  <SegmentedControl
                    data={CONTAINERS.map((c) => ({ value: String(c), label: String(c) }))}
                    value={String(container)}
                    onChange={(v) => setContainer(Number(v))}
                  />
                </Stack>
                <Select
                  label="Slot"
                  placeholder="Choose a free slot"
                  data={SLOTS.map((s) => {
                    const taken = occupant(container, s);
                    return {
                      value: String(s),
                      label: taken ? `${s} — ${taken.barcode}` : String(s),
                      disabled: Boolean(taken),
                    };
                  })}
                  value={slot === null ? null : String(slot)}
                  onChange={(v) => setSlot(v === null ? null : Number(v))}
                  w={200}
                />
                <Button disabled={slot === null} loading={store.isPending} onClick={save}>
                  Store
                </Button>
              </Group>
            )}
          </>
        )}
      </Stack>
    </Card>
  );
}

function OccupancyGrid({
  occupant,
  selected,
  onPick,
}: {
  occupant: (c: number, s: number) => StoredFrame | undefined;
  selected: { container: number; slot: number | null } | null;
  onPick: (container: number, slot: number) => void;
}) {
  return (
    <SimpleGrid cols={{ base: 1, sm: 3 }} maw={900}>
      {CONTAINERS.map((c) => (
        <Card withBorder key={c} p="xs">
          <Text fw={600} size="sm" mb={4}>
            Container {c}
          </Text>
          <Stack gap={2}>
            {SLOTS.map((s) => {
              const frame = occupant(c, s);
              const isSelected = selected?.container === c && selected.slot === s;
              const atBeamline = frame && frame.state !== "internal_storage";
              // Warning: the scheduler skips unlocked frames, so they will not be measured.
              const notLocked = frame && !atBeamline && !frame.locked;
              const cellStyle = {
                borderRadius: 4,
                background: isSelected
                  ? "var(--mantine-color-orange-light)"
                  : frame
                    ? atBeamline
                      ? `var(--mantine-color-${IN_PROGRESS_COLOR}-light)`
                      : notLocked
                        ? "var(--mantine-color-yellow-light)"
                        : "var(--mantine-primary-color-light)"
                    : undefined,
                border: "1px solid var(--mantine-color-default-border)",
              };
              if (!frame) {
                // A free slot: click it to choose it for the frame being stored.
                return (
                  <UnstyledButton
                    key={s}
                    disabled={!selected}
                    onClick={() => onPick(c, s)}
                    aria-label={`Container ${c} slot ${s}: free`}
                  >
                    <Box px="xs" py={2} style={cellStyle}>
                      <Group gap="xs" wrap="nowrap" mih={22}>
                        <Text size="xs" c="dimmed" w={18}>
                          {s}
                        </Text>
                        <Text size="xs" c="dimmed">
                          free
                        </Text>
                      </Group>
                    </Box>
                  </UnstyledButton>
                );
              }
              return (
                <Box key={s} px="xs" py={2} style={cellStyle} aria-label={`Container ${c} slot ${s}: ${frame.barcode}`}>
                  <Group gap="xs" wrap="nowrap" justify="space-between">
                    <Group gap="xs" wrap="nowrap">
                      <Text size="xs" c="dimmed" w={18}>
                        {s}
                      </Text>
                      <Text size="xs" ff="monospace">
                        {frame.barcode}
                      </Text>
                      {notLocked && (
                        <Tooltip label="Not locked: will not be measured until locked" withArrow>
                          <Text size="xs" fw={600} c="var(--mantine-color-yellow-light-color)">
                            not locked
                          </Text>
                        </Tooltip>
                      )}
                      {atBeamline && (
                        <Text size="xs" c="dimmed">
                          {FRAME_STATE_LABELS[frame.state]}
                        </Text>
                      )}
                    </Group>
                    <SlotActions frame={frame} />
                  </Group>
                </Box>
              );
            })}
          </Stack>
        </Card>
      ))}
    </SimpleGrid>
  );
}

/**
 * Buttons on an occupied slot:
 * - in its slot: move to external storage (frees the slot), immediately;
 * - scheduled or loaded: release it back into its slot (after a control-software crash),
 *   after confirmation.
 */
function SlotActions({ frame }: { frame: StoredFrame }) {
  const apply = useApplyScan();
  const release = useRelease();
  const [confirming, setConfirming] = useState(false);
  const notify = (ok: boolean, message: string) =>
    notifications.show({ color: ok ? "green" : "red", message });

  if (frame.state === "internal_storage") {
    return (
      <Tooltip label="move to external storage" withArrow>
        <ActionIcon
          variant="light"
          color="teal"
          size="sm"
          aria-label={`move ${frame.barcode} to external storage`}
          loading={apply.isPending}
          onClick={() =>
            apply.mutate(
              { action: "external_storage", barcodes: [frame.barcode] },
              {
                onSuccess: ([result]) =>
                  result?.moved
                    ? notify(true, `${frame.barcode} moved to external storage`)
                    : notify(false, `${frame.barcode}: ${result?.problem ?? "not moved"}`),
                onError: (err) => notify(false, err.message),
              },
            )
          }
        >
          <IconBuildingWarehouse size={14} />
        </ActionIcon>
      </Tooltip>
    );
  }
  return (
    <>
      <Tooltip label="release: back into this slot (control software stopped)" withArrow>
        <ActionIcon
          variant="light"
          color="orange"
          size="sm"
          aria-label={`release ${frame.barcode} back into its slot`}
          loading={release.isPending}
          onClick={() => setConfirming(true)}
        >
          <IconArrowBackUp size={14} />
        </ActionIcon>
      </Tooltip>
      <Modal opened={confirming} onClose={() => setConfirming(false)} title="Release frame">
        <Stack>
          <Text size="sm">
            Use this when the control software stopped while handling <b>{frame.barcode}</b>. Put
            the frame back into container {frame.container}, slot {frame.slot} by hand first,
            then release it here before restarting the control software.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              color="orange"
              loading={release.isPending}
              onClick={() =>
                release.mutate(frame.barcode, {
                  onSuccess: () => {
                    setConfirming(false);
                    notify(true, `${frame.barcode} released back into its slot`);
                  },
                  onError: (err) => notify(false, err.message),
                })
              }
            >
              Release
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

function StoredTable({ rows }: { rows: StoredFrame[] }) {
  if (rows.length === 0) return <Text c="dimmed">No frames in internal storage.</Text>;
  return (
    <Table.ScrollContainer minWidth={860}>
      <Table striped aria-label="Frames in internal storage">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Container</Table.Th>
            <Table.Th>Slot</Table.Th>
            <Table.Th>In storage since</Table.Th>
            <Table.Th>Barcode</Table.Th>
            <Table.Th>User</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Locked</Table.Th>
            <Table.Th>Edges</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r) => (
            <Table.Tr key={r.barcode}>
              <Table.Td>{r.container}</Table.Td>
              <Table.Td>{r.slot}</Table.Td>
              <Table.Td>{r.since ? formatDateTime(r.since) : "—"}</Table.Td>
              <Table.Td>
                <Anchor component={Link} to={`/frames/${r.barcode}`} ff="monospace">
                  {r.barcode}
                </Anchor>
              </Table.Td>
              <Table.Td>{r.owner?.name}</Table.Td>
              <Table.Td>
                <FrameStateBadge state={r.state} />
              </Table.Td>
              <Table.Td>
                <YesNoIcon value={r.locked} />
              </Table.Td>
              <Table.Td>{r.edges.join(", ") || "—"}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
