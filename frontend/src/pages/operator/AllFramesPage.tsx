import {
  Alert,
  Anchor,
  Group,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { IconLock, IconSearch, IconShieldCheck } from "@tabler/icons-react";
import { useState } from "react";
import { Link } from "react-router";

import type { Frame, FrameState } from "../../api/client";
import { useFrames, usePlateTypes } from "../../api/materials";
import { PageLoader } from "../../auth/guards";
import { DataLink } from "../../data/DataLink";
import { plateSummary, statusSince } from "../../frames/summary";
import { formatDate, formatDateTime, FRAME_STATE_LABELS } from "../../materials/labels";
import { FrameStateBadge } from "../../frames/FrameStateBadge";

/** All issued frames, for Operators (requirements §9.5). */
export function AllFramesPage() {
  const [state, setState] = useState<FrameState | null>(null);
  const [query, setQuery] = useState("");
  const { data: frames, isPending, error } = useFrames({ allUsers: true, state: state ?? undefined });
  const { data: plateTypes = [] } = usePlateTypes();

  const needle = query.trim().toLowerCase();
  // Reserved barcodes have no owner yet; they are listed on the Barcodes page.
  const shown = (frames ?? []).filter(
    (f) =>
      f.state !== "reserved" &&
      (!needle ||
        [f.barcode, f.owner?.name ?? "", f.note].join(" ").toLowerCase().includes(needle)),
  );

  return (
    <Stack>
      <Title order={2}>All Frames</Title>
      <Group>
        <TextInput
          aria-label="Search frames"
          placeholder="Search by barcode, user or note"
          leftSection={<IconSearch size={16} />}
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          w={320}
        />
        <Select
          aria-label="Status"
          placeholder="Any status"
          clearable
          data={Object.entries(FRAME_STATE_LABELS)
            .filter(([value]) => value !== "reserved")
            .map(([value, label]) => ({ value, label }))}
          value={state}
          onChange={(value) => setState(value as FrameState | null)}
          w={220}
        />
      </Group>
      {isPending ? (
        <PageLoader />
      ) : error ? (
        <Alert color="red">{error.message}</Alert>
      ) : shown.length === 0 ? (
        <Text c="dimmed">No frames.</Text>
      ) : (
        <Table.ScrollContainer minWidth={800}>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Barcode</Table.Th>
                <Table.Th>User</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Since</Table.Th>
                <Table.Th>Plates</Table.Th>
                <Table.Th>Samples</Table.Th>
                <Table.Th>Safe / locked</Table.Th>
                <Table.Th>Note</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {shown.map((frame) => (
                <Table.Tr key={frame.barcode}>
                  <Table.Td>
                    <Group gap={6} wrap="nowrap">
                      <Anchor component={Link} to={`/frames/${frame.barcode}`} ff="monospace">
                        {frame.barcode}
                      </Anchor>
                      {frame.has_data && <DataLink barcode={frame.barcode} />}
                    </Group>
                  </Table.Td>
                  <Table.Td>{frame.owner?.name}</Table.Td>
                  <Table.Td>
                    <FrameStateBadge state={frame.state} />
                  </Table.Td>
                  <Table.Td>
                    <StatusSince frame={frame} />
                  </Table.Td>
                  <Table.Td>{plateSummary(frame, plateTypes)}</Table.Td>
                  <Table.Td>{frame.positions.length || "—"}</Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      {frame.safety && <IconShieldCheck size={16} aria-label="declared safe" />}
                      {frame.locked && <IconLock size={16} aria-label="locked" />}
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" lineClamp={1}>
                      {frame.note}
                    </Text>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Stack>
  );
}

/** Date the frame entered its current status; time and who did it on hover. */
function StatusSince({ frame }: { frame: Frame }) {
  const event = statusSince(frame);
  if (!event) return <Text size="sm">—</Text>;
  return (
    <Tooltip label={`${formatDateTime(event.at)} by ${event.by}`} withArrow>
      <Text size="sm" style={{ whiteSpace: "nowrap" }}>
        {formatDate(event.at)}
      </Text>
    </Tooltip>
  );
}
