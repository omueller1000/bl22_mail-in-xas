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
import { IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import type { Frame, PlateType } from "../api/client";
import {
  useAssignSample,
  useClearPosition,
  useFrame,
  useSetNote,
  useSetPlates,
} from "../api/frames";
import { usePlateTypes } from "../api/materials";
import { useSamples } from "../api/samples";
import { PageLoader } from "../auth/guards";
import { FrameView } from "../frames/FrameView";
import { SamplePicker } from "../frames/SamplePicker";
import { FRAME_STATE_LABELS } from "../materials/labels";

const CONFIGURABLE_STATES = ["issued", "shipped_to_user"];

/** Mount plates and place samples on a frame (requirements §8.1). */
export function FrameConfigPage() {
  const { barcode = "" } = useParams();
  const { data: frame, isPending, error } = useFrame(barcode);
  const { data: plateTypes } = usePlateTypes();
  const [position, setPosition] = useState<string | null>(null);

  if (isPending || !plateTypes) return <PageLoader />;
  if (error) return <Alert color="red">{error.message}</Alert>;

  const readOnlyReason = frame.safety
    ? "This frame has been declared safe; plates and samples can no longer change."
    : !CONFIGURABLE_STATES.includes(frame.state)
      ? "This frame is no longer with you; plates and samples can no longer change."
      : null;

  return (
    <Stack>
      <Anchor component={Link} to="/frames" size="sm">
        ← All frames
      </Anchor>
      <Group>
        <Title order={2} ff="monospace">
          {frame.barcode}
        </Title>
        <Badge variant="light">{FRAME_STATE_LABELS[frame.state]}</Badge>
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
            <PositionsCard frame={frame} disabled={Boolean(readOnlyReason)} />
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

function PositionsCard({ frame, disabled }: { frame: Frame; disabled: boolean }) {
  const clear = useClearPosition(frame);

  return (
    <Card withBorder>
      <Text fw={600} mb="xs">
        Samples
      </Text>
      {frame.positions.length === 0 ? (
        <Text size="sm" c="dimmed">
          Click a position on the frame to place a sample.
        </Text>
      ) : (
        <Stack gap={2}>
          {frame.positions.map((p) => (
            <Group key={p.position} gap="xs" wrap="nowrap">
              <Text size="sm" ff="monospace" w={70}>
                {p.position}
              </Text>
              <Text size="sm" style={{ flex: 1 }}>
                {p.sample_name}
              </Text>
              {!disabled && (
                <Tooltip label="Remove from this position" withArrow>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    size="sm"
                    aria-label={`Remove ${p.sample_name} from ${p.position}`}
                    loading={clear.isPending && clear.variables === p.position}
                    disabled={clear.isPending}
                    onClick={() =>
                      clear.mutate(p.position, {
                        onError: (err) => notifications.show({ color: "red", message: err.message }),
                      })
                    }
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Tooltip>
              )}
            </Group>
          ))}
        </Stack>
      )}
    </Card>
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
