import {
  Alert,
  Button,
  Card,
  Group,
  NumberInput,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useState } from "react";

import { useFrames, useReserveBarcodes } from "../../api/materials";
import { PageLoader } from "../../auth/guards";
import { CopyIcon } from "../../components/CopyIcon";
import { formatDate } from "../../materials/labels";

/** Generate new barcodes for printing labels; list barcodes not yet issued (requirements §6.1). */
export function BarcodesPage() {
  const [count, setCount] = useState<number | string>(10);
  const [latest, setLatest] = useState<string[]>([]);
  const reserve = useReserveBarcodes();
  const { data: reserved, isPending } = useFrames({ allUsers: true, state: "reserved" });

  return (
    <Stack>
      <Title order={2}>Generate Barcodes</Title>
      <Card withBorder maw={640}>
        <Stack>
          <Text size="sm">
            Generate new, never-used barcodes. Print them as Code128 labels, then scan them to issue frames
            for material requests.
          </Text>
          <Group align="flex-end">
            <NumberInput
              label="Number of barcodes"
              min={1}
              max={200}
              allowDecimal={false}
              value={count}
              onChange={setCount}
              w={180}
            />
            <Button
              loading={reserve.isPending}
              disabled={typeof count !== "number" || count < 1 || count > 200}
              onClick={() =>
                reserve.mutate(count as number, {
                  onSuccess: (frames) => setLatest(frames.map((f) => f.barcode)),
                })
              }
            >
              Generate
            </Button>
          </Group>
          {reserve.isError && <Alert color="red">{reserve.error.message}</Alert>}
          {latest.length > 0 && (
            <Stack gap="xs">
              <Group gap="xs">
                <Text fw={600}>New barcodes ({latest.length})</Text>
                <CopyIcon value={latest.join("\n")} label="all new barcodes" />
              </Group>
              <Text ff="monospace" style={{ whiteSpace: "pre-wrap" }}>
                {latest.join("\n")}
              </Text>
            </Stack>
          )}
        </Stack>
      </Card>

      <Title order={3}>Reserved, not yet issued{reserved && ` (${reserved.length})`}</Title>
      {isPending ? (
        <PageLoader />
      ) : !reserved || reserved.length === 0 ? (
        <Text c="dimmed">None.</Text>
      ) : (
        <Table striped maw={640}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Barcode</Table.Th>
              <Table.Th>Generated</Table.Th>
              <Table.Th>By</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {reserved.map((frame) => (
              <Table.Tr key={frame.barcode}>
                <Table.Td ff="monospace">{frame.barcode}</Table.Td>
                <Table.Td>{formatDate(frame.created_at)}</Table.Td>
                <Table.Td>{frame.history[0]?.by}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
