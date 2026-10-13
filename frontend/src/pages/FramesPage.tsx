import { Alert, Anchor, Badge, Stack, Table, Text, Title } from "@mantine/core";
import { Link } from "react-router";

import { useFrames, usePlateTypes } from "../api/materials";
import { PageLoader } from "../auth/guards";
import { plateSummary } from "../frames/summary";
import { FRAME_STATE_LABELS } from "../materials/labels";

/** The user's frames (barcodes issued to them); each opens the configuration page. */
export function FramesPage() {
  const { data: frames, isPending, error } = useFrames();
  const { data: plateTypes = [] } = usePlateTypes();

  return (
    <Stack>
      <Title order={2}>Frames</Title>
      <Text c="dimmed" size="sm">
        Frames we have issued to you. Open one to mount plates and place your samples.
      </Text>
      {isPending ? (
        <PageLoader />
      ) : error ? (
        <Alert color="red">{error.message}</Alert>
      ) : frames.length === 0 ? (
        <Text c="dimmed">
          No frames yet. <Anchor component={Link} to="/materials">Request materials</Anchor> to get
          some.
        </Text>
      ) : (
        <Table.ScrollContainer minWidth={640}>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Barcode</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Plates</Table.Th>
                <Table.Th>Samples</Table.Th>
                <Table.Th>Note</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {frames.map((frame) => (
                <Table.Tr key={frame.barcode}>
                  <Table.Td>
                    <Anchor component={Link} to={`/frames/${frame.barcode}`} ff="monospace">
                      {frame.barcode}
                    </Anchor>
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="light">{FRAME_STATE_LABELS[frame.state]}</Badge>
                  </Table.Td>
                  <Table.Td>{plateSummary(frame, plateTypes)}</Table.Td>
                  <Table.Td>{frame.positions.length || "—"}</Table.Td>
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
