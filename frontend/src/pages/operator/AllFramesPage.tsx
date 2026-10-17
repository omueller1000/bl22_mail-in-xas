import { Anchor, Group, Select, Stack, Text, TextInput, Title, Tooltip } from "@mantine/core";
import { IconLock, IconSearch, IconShieldCheck } from "@tabler/icons-react";
import { useState } from "react";
import { Link } from "react-router";

import type { Frame, FrameState } from "../../api/client";
import { useAllFrames, usePlateTypes } from "../../api/materials";
import { type PagedColumn, PagedTable } from "../../components/PagedTable";
import { usePaging } from "../../components/paging";
import { DataLink } from "../../data/DataLink";
import { plateSummary, statusSince } from "../../frames/summary";
import { formatDate, formatDateTime, FRAME_STATE_LABELS } from "../../materials/labels";
import { FrameStateBadge } from "../../frames/FrameStateBadge";

/** All users' frames, paged on the server, for Operators (requirements §9.5). */
export function AllFramesPage() {
  const [state, setState] = useState<FrameState | null>(null);
  const paging = usePaging<"barcode">({ sort: "barcode", order: "asc" });
  const frames = useAllFrames({ ...paging.params, state: state ?? undefined });
  const { data: plateTypes = [] } = usePlateTypes();

  const columns: PagedColumn<Frame, "barcode">[] = [
    {
      key: "barcode",
      label: "Barcode",
      sort: "barcode",
      render: (frame) => (
        <Group gap={6} wrap="nowrap">
          <Anchor component={Link} to={`/frames/${frame.barcode}`} ff="monospace">
            {frame.barcode}
          </Anchor>
          {frame.has_data && <DataLink barcode={frame.barcode} />}
        </Group>
      ),
    },
    { key: "user", label: "User", render: (frame) => frame.owner?.name },
    { key: "status", label: "Status", render: (frame) => <FrameStateBadge state={frame.state} /> },
    { key: "since", label: "Since", render: (frame) => <StatusSince frame={frame} /> },
    { key: "plates", label: "Plates", render: (frame) => plateSummary(frame, plateTypes) },
    { key: "samples", label: "Samples", render: (frame) => frame.positions.length || "—" },
    {
      key: "safe",
      label: "Safe / locked",
      render: (frame) => (
        <Group gap={4}>
          {frame.safety && <IconShieldCheck size={16} aria-label="declared safe" />}
          {frame.locked && <IconLock size={16} aria-label="locked" />}
        </Group>
      ),
    },
    {
      key: "note",
      label: "Note",
      render: (frame) => (
        <Text size="sm" lineClamp={1}>
          {frame.note}
        </Text>
      ),
    },
  ];

  return (
    <Stack>
      <Title order={2}>All Frames</Title>
      <Group>
        <TextInput
          aria-label="Search frames"
          placeholder="Search by barcode, user or note"
          leftSection={<IconSearch size={16} />}
          value={paging.search}
          onChange={(event) => paging.setSearch(event.currentTarget.value)}
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
          onChange={(value) => {
            setState(value as FrameState | null);
            paging.firstPage();
          }}
          w={220}
        />
      </Group>
      <PagedTable
        columns={columns}
        paging={paging}
        query={frames}
        rowKey={(frame) => frame.barcode}
        empty="No frames."
      />
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
