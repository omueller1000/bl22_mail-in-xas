import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Grid,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  Textarea,
  Title,
  Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { useMe } from "../api/auth";
import type { Frame, Measurement, PlateType } from "../api/client";
import {
  useAssignSample,
  useClearPosition,
  useFrame,
  useSetNote,
  useSetPlates,
} from "../api/frames";
import { usePlateTypes } from "../api/materials";
import {
  useDeleteMeasurement,
  useMeasurementOptions,
  useMeasurements,
} from "../api/measurements";
import { useSamples } from "../api/samples";
import { useRelease } from "../api/scanning";
import { PageLoader } from "../auth/guards";
import { hasRole } from "../auth/roles";
import { FrameView } from "../frames/FrameView";
import { MeasurementModal } from "../frames/MeasurementModal";
import { describeMeasurement, MEASUREMENT_STATUS } from "../frames/measurementText";
import { SafetyCard } from "../frames/SafetyCard";
import { SamplePicker } from "../frames/SamplePicker";
import { FrameStateBadge } from "../frames/FrameStateBadge";

const CONFIGURABLE_STATES = ["issued", "shipped_to_user"];
const MEASUREMENTS_FROZEN_STATES = ["scheduled", "loaded", "returned", "void"];

/** Mount plates, place samples, define measurements, declare safety and lock (§6.4, §8). */
export function FrameConfigPage() {
  const { barcode = "" } = useParams();
  const { data: frame, isPending, error } = useFrame(barcode);
  const { data: plateTypes } = usePlateTypes();
  const { data: me } = useMe();
  const [position, setPosition] = useState<string | null>(null);

  if (isPending || !plateTypes) return <PageLoader />;
  if (error) return <Alert color="red">{error.message}</Alert>;

  const isOwner = Boolean(me?.user && frame.owner?.id === me.user.id);
  const isOperator = Boolean(me?.user && hasRole(me.user.role, "operator"));
  // Plates, note and sample placement: owner only (requirements §6.6).
  const readOnlyReason = !isOwner
    ? `This is ${frame.owner?.name ?? "another user"}'s frame. Only the owner can change plates and samples.`
    : frame.safety
      ? "This frame has been declared safe; plates and samples can no longer change."
      : !CONFIGURABLE_STATES.includes(frame.state)
        ? "This frame is no longer with you; plates and samples can no longer change."
        : null;
  // Measurements: owner or Operator, while unlocked and not being measured.
  const measurementsEditable =
    !frame.locked && !MEASUREMENTS_FROZEN_STATES.includes(frame.state);

  return (
    <Stack>
      <Anchor component={Link} to={isOwner ? "/frames" : "/operator/frames"} size="sm">
        ← All frames
      </Anchor>
      <Group>
        <Title order={2} ff="monospace">
          {frame.barcode}
        </Title>
        <FrameStateBadge state={frame.state} />
        {frame.storage && (
          <Badge variant="outline" color="gray">
            Container {frame.storage.container} · Slot {frame.storage.slot}
          </Badge>
        )}
        {isOperator && ["scheduled", "loaded"].includes(frame.state) && (
          <ReleaseButton barcode={frame.barcode} />
        )}
      </Group>
      {readOnlyReason && <Alert color="gray">{readOnlyReason}</Alert>}
      <Grid gap="xl">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <FrameView
            frame={frame}
            plateTypes={plateTypes}
            selected={position}
            onPositionClick={readOnlyReason ? undefined : setPosition}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Stack>
            <PlatesCard frame={frame} plateTypes={plateTypes} disabled={Boolean(readOnlyReason)} />
            <NoteCard key={frame.version} frame={frame} disabled={Boolean(readOnlyReason)} />
            <PositionsCard
              frame={frame}
              configurable={!readOnlyReason}
              measurementsEditable={measurementsEditable}
            />
            <SafetyCard frame={frame} isOwner={isOwner} />
          </Stack>
        </Grid.Col>
      </Grid>
      {position && (
        <PositionModal frame={frame} position={position} onClose={() => setPosition(null)} />
      )}
    </Stack>
  );
}

function PlatesCard({
  frame,
  plateTypes,
  disabled,
}: {
  frame: Frame;
  plateTypes: PlateType[];
  disabled: boolean;
}) {
  const setPlates = useSetPlates(frame);
  const [pending, setPending] = useState<{ left: string | null; right: string | null } | null>(
    null,
  );
  const leftType = plateTypes.find((t) => t.id === frame.plates.left);

  const options = (side: "left" | "right") =>
    plateTypes
      .filter((t) => t.sides.includes(side))
      .map((t) => ({
        value: t.id,
        label: t.blocks_other_side ? `${t.name} (whole frame)` : t.name,
      }));

  /** Positions that a plate change would clear. */
  const affected = (next: { left: string | null; right: string | null }) =>
    frame.positions.filter((p) => {
      const side = p.position.startsWith("Left") ? "left" : "right";
      return next[side] !== frame.plates[side];
    });

  const change = (next: { left: string | null; right: string | null }) => {
    // A plate spanning the whole frame leaves no room on the right.
    if (plateTypes.find((t) => t.id === next.left)?.blocks_other_side) next = { ...next, right: null };
    if (affected(next).length > 0) setPending(next);
    else apply(next);
  };

  const apply = (next: { left: string | null; right: string | null }) =>
    setPlates.mutate(next, {
      onSuccess: () => setPending(null),
      onError: (err) => notifications.show({ color: "red", message: err.message }),
    });

  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={600}>Plates</Text>
        <Group grow align="flex-start">
          <Select
            label="Left"
            placeholder="empty"
            clearable
            data={options("left")}
            value={frame.plates.left ?? null}
            disabled={disabled || setPlates.isPending}
            onChange={(value) => change({ left: value, right: frame.plates.right ?? null })}
          />
          <Select
            label="Right"
            placeholder={leftType?.blocks_other_side ? "covered by the left plate" : "empty"}
            clearable
            data={options("right")}
            value={frame.plates.right ?? null}
            disabled={disabled || setPlates.isPending || Boolean(leftType?.blocks_other_side)}
            onChange={(value) => change({ left: frame.plates.left ?? null, right: value })}
          />
        </Group>
      </Stack>
      <Modal opened={pending !== null} onClose={() => setPending(null)} title="Change plates">
        {pending && (
          <Stack>
            <Text>
              This removes the samples (and their measurements) from{" "}
              {affected(pending)
                .map((p) => p.position)
                .join(", ")}
              . Continue?
            </Text>
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setPending(null)}>
                Cancel
              </Button>
              <Button color="red" loading={setPlates.isPending} onClick={() => apply(pending)}>
                Change plates
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Card>
  );
}

function NoteCard({ frame, disabled }: { frame: Frame; disabled: boolean }) {
  const [note, setNote] = useState(frame.note);
  const setFrameNote = useSetNote(frame);
  const changed = note.trim() !== frame.note;

  return (
    <Card withBorder>
      <Stack gap="sm">
        <Textarea
          label="Note"
          description="For yourself and the beamline staff, e.g. “batch 2, Fe catalysts”"
          autosize
          minRows={2}
          maxLength={500}
          value={note}
          disabled={disabled}
          onChange={(event) => setNote(event.currentTarget.value)}
        />
        {changed && (
          <Group justify="flex-end">
            <Button
              size="xs"
              loading={setFrameNote.isPending}
              onClick={() =>
                setFrameNote.mutate(note.trim(), {
                  onError: (err) => notifications.show({ color: "red", message: err.message }),
                })
              }
            >
              Save note
            </Button>
          </Group>
        )}
      </Stack>
    </Card>
  );
}

function PositionsCard({
  frame,
  configurable,
  measurementsEditable,
}: {
  frame: Frame;
  /** Samples can be removed (owner, before the safety declaration). */
  configurable: boolean;
  /** Measurements can be added, edited and deleted (frame unlocked, not being measured). */
  measurementsEditable: boolean;
}) {
  const clear = useClearPosition(frame);
  const { data: measurements = [] } = useMeasurements(frame.barcode);
  const { data: options } = useMeasurementOptions();
  const remove = useDeleteMeasurement(frame);
  const [editing, setEditing] = useState<{ position: string; measurement?: Measurement } | null>(
    null,
  );
  const fail = (err: Error) => notifications.show({ color: "red", message: err.message });

  return (
    <Card withBorder>
      <Text fw={600} mb="xs">
        Samples and measurements
      </Text>
      {frame.positions.length === 0 ? (
        <Text size="sm" c="dimmed">
          Click a position on the frame to place a sample.
        </Text>
      ) : (
        <Stack gap="sm">
          {frame.positions.map((p) => {
            const ofPosition = measurements.filter((m) => m.position === p.position);
            return (
              <Stack key={p.position} gap={4}>
                <Group gap="xs" wrap="nowrap">
                  <Text size="sm" ff="monospace" fw={600} w={70}>
                    {p.position}
                  </Text>
                  <Text size="sm" fw={500} style={{ flex: 1 }}>
                    {p.sample_name}
                  </Text>
                  {configurable && (
                    <Tooltip label="Remove from this position" withArrow>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        size="sm"
                        aria-label={`Remove ${p.sample_name} from ${p.position}`}
                        loading={clear.isPending && clear.variables === p.position}
                        disabled={clear.isPending}
                        onClick={() => clear.mutate(p.position, { onError: fail })}
                      >
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Tooltip>
                  )}
                </Group>
                {ofPosition.map((m) => (
                  <Group key={m.id} gap="xs" wrap="nowrap" pl={78}>
                    <Text size="sm" style={{ flex: 1 }}>
                      {describeMeasurement(m, options)}
                    </Text>
                    <Badge size="sm" variant="light" color={MEASUREMENT_STATUS[m.status].color}>
                      {MEASUREMENT_STATUS[m.status].label}
                    </Badge>
                    {measurementsEditable && (
                      <>
                        <Tooltip label="Edit measurement" withArrow>
                          <ActionIcon
                            variant="subtle"
                            color="gray"
                            size="sm"
                            aria-label={`Edit measurement ${m.number} at ${p.position}`}
                            onClick={() => setEditing({ position: p.position, measurement: m })}
                          >
                            <IconPencil size={16} />
                          </ActionIcon>
                        </Tooltip>
                        <Tooltip
                          label={m.executed ? "Already run; cannot be deleted" : "Delete measurement"}
                          withArrow
                        >
                          <ActionIcon
                            variant="subtle"
                            color="red"
                            size="sm"
                            aria-label={`Delete measurement ${m.number} at ${p.position}`}
                            disabled={m.executed || remove.isPending}
                            loading={remove.isPending && remove.variables === m.id}
                            onClick={() => remove.mutate(m.id, { onError: fail })}
                          >
                            <IconTrash size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </>
                    )}
                  </Group>
                ))}
                {measurementsEditable && (
                  <Group pl={78}>
                    <Button
                      size="compact-xs"
                      variant="light"
                      leftSection={<IconPlus size={14} />}
                      onClick={() => setEditing({ position: p.position })}
                    >
                      Add measurement
                    </Button>
                  </Group>
                )}
              </Stack>
            );
          })}
        </Stack>
      )}
      {editing && (
        <MeasurementModal
          frame={frame}
          position={editing.position}
          sampleName={
            frame.positions.find((p) => p.position === editing.position)?.sample_name ?? ""
          }
          measurement={editing.measurement}
          onClose={() => setEditing(null)}
        />
      )}
    </Card>
  );
}

/** Operator override after a control-software crash: back into its internal-storage slot. */
function ReleaseButton({ barcode }: { barcode: string }) {
  const [confirming, setConfirming] = useState(false);
  const release = useRelease();
  return (
    <>
      <Button size="xs" variant="light" color="orange" onClick={() => setConfirming(true)}>
        Release to internal storage
      </Button>
      <Modal opened={confirming} onClose={() => setConfirming(false)} title="Release frame">
        <Stack>
          <Text size="sm">
            Use this when the control software stopped while handling {barcode}. Put the frame
            back into its slot by hand first, then release it here before restarting the control
            software.
          </Text>
          {release.isError && <Alert color="red">{release.error.message}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              color="orange"
              loading={release.isPending}
              onClick={() => release.mutate(barcode, { onSuccess: () => setConfirming(false) })}
            >
              Release
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

/** Sample id -> positions it occupies on this frame. */
function placementsBySample(frame: Frame): Map<string, string[]> {
  const result = new Map<string, string[]>();
  for (const p of frame.positions) {
    result.set(p.sample_id, [...(result.get(p.sample_id) ?? []), p.position]);
  }
  return result;
}

/** Choose, change or remove the sample at one position. */
function PositionModal({
  frame,
  position,
  onClose,
}: {
  frame: Frame;
  position: string;
  onClose: () => void;
}) {
  const current = frame.positions.find((p) => p.position === position);
  const [sampleId, setSampleId] = useState<string | null>(current?.sample_id ?? null);
  const { data: samples = [], isPending } = useSamples(); // non-archived, newest first
  const assign = useAssignSample(frame);
  const clear = useClearPosition(frame);
  const fail = (err: Error) => notifications.show({ color: "red", message: err.message });

  return (
    <Modal
      opened
      onClose={onClose}
      title={`Position ${position}`}
      size="lg"
      // Left-aligned with the same margin as at the top, so the Samples card stays visible.
      xOffset="5dvh"
      styles={{ inner: { justifyContent: "flex-start" } }}
    >
      <Stack>
        {samples.length === 0 && !isPending ? (
          <Text size="sm">
            You have no samples yet.{" "}
            <Anchor component={Link} to="/samples">
              Create one on the Samples page
            </Anchor>
            .
          </Text>
        ) : (
          <SamplePicker
            samples={samples}
            selectedId={sampleId}
            onSelect={setSampleId}
            placements={placementsBySample(frame)}
          />
        )}
        <Group justify="space-between">
          {current ? (
            <Button
              variant="subtle"
              color="red"
              loading={clear.isPending}
              onClick={() => clear.mutate(position, { onSuccess: onClose, onError: fail })}
            >
              Remove sample
            </Button>
          ) : (
            <span />
          )}
          <Group>
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button
              disabled={!sampleId || sampleId === current?.sample_id}
              loading={assign.isPending}
              onClick={() =>
                sampleId &&
                assign.mutate({ position, sampleId }, { onSuccess: onClose, onError: fail })
              }
            >
              Place sample
            </Button>
          </Group>
        </Group>
      </Stack>
    </Modal>
  );
}
