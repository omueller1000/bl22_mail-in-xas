import {
  Alert,
  Button,
  Card,
  ColorSwatch,
  Group,
  Progress,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { IconRefresh } from "@tabler/icons-react";

import type { components } from "../../api/schema";
import { useSystemStatus } from "../../api/status";
import { PageLoader } from "../../auth/guards";
import { formatBytes, formatDateTime } from "../../materials/labels";

type SystemStatus = components["schemas"]["SystemStatus"];
type DatabaseStatus = components["schemas"]["DatabaseStatus"];

// Disk usage from which the bar turns yellow (warning) and red.
const DISK_WARNING = 0.8;
const DISK_CRITICAL = 0.9;
// Beyond this the growth forecast is meaningless.
const MAX_FORECAST_DAYS = 3650;
// The portal's own database in the disk bar (other data uses the blue/yellow/red level colour).
const OWN_COLOR = "grape";

/** The state of the system; for now the capacity of the MongoDB server. */
export function StatusPage() {
  const { data: status, isPending, error, refetch, isFetching } = useSystemStatus();

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Status</Title>
        <Button
          variant="default"
          leftSection={<IconRefresh size={16} />}
          loading={isFetching}
          onClick={() => void refetch()}
        >
          Refresh
        </Button>
      </Group>
      {isPending ? (
        <PageLoader />
      ) : error ? (
        <Alert color="red">{error.message}</Alert>
      ) : (
        <>
          <Text c="dimmed" size="sm">
            Checked {formatDateTime(status.checked_at)}.
          </Text>
          <DatabaseCard database={status.database} checkedAt={status.checked_at} />
          <PortalCard status={status} />
        </>
      )}
    </Stack>
  );
}

function DatabaseCard({ database, checkedAt }: { database: DatabaseStatus; checkedAt: string }) {
  const { disk, growth } = database;
  const fraction = disk.total_bytes ? disk.used_bytes / disk.total_bytes : 0;
  const color = fraction >= DISK_CRITICAL ? "red" : fraction >= DISK_WARNING ? "yellow" : "blue";
  const free = Math.max(disk.total_bytes - disk.used_bytes, 0);
  const own = database.storage_bytes + database.index_bytes;
  const other = Math.max(disk.used_bytes - own, 0);
  // At least a sliver, so the portal's share stays visible next to terabytes of other data.
  const ownPercent = disk.total_bytes
    ? Math.min(Math.max((own / disk.total_bytes) * 100, own > 0 ? 1 : 0), fraction * 100)
    : 0;
  const daysUntilFull = growth.days_until_full ?? null;
  const fullOn =
    daysUntilFull === null
      ? null
      : new Date(new Date(checkedAt).getTime() + daysUntilFull * 86_400_000);

  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={600}>Database</Text>
        {fraction >= DISK_WARNING && (
          <Alert color={color}>
            The MongoDB disk is {Math.round(fraction * 100)}% full. Measured data can no longer be
            stored once it is full.
          </Alert>
        )}
        <Stack gap={4}>
          <Group justify="space-between">
            <Text size="sm">MongoDB disk</Text>
            <Text size="sm">
              {formatBytes(disk.used_bytes)} of {formatBytes(disk.total_bytes)} used,{" "}
              <b>{formatBytes(free)} free</b>
            </Text>
          </Group>
          <Progress.Root size="xl">
            <Tooltip label={`This database (${database.name}): ${formatBytes(own)}`} withArrow>
              <Progress.Section
                value={ownPercent}
                color={OWN_COLOR}
                aria-label={`This database: ${formatBytes(own)}`}
              />
            </Tooltip>
            <Tooltip label={`Other data on the disk: ${formatBytes(other)}`} withArrow>
              <Progress.Section
                value={fraction * 100 - ownPercent}
                color={color}
                aria-label={`Disk ${Math.round(fraction * 100)}% used`}
              />
            </Tooltip>
          </Progress.Root>
          <Group gap="md">
            <Legend color={OWN_COLOR} label={`This database (${database.name}): ${formatBytes(own)}`} />
            <Legend color={color} label={`Other data on the disk: ${formatBytes(other)}`} />
            <Legend color="gray.2" label={`Free: ${formatBytes(free)}`} />
          </Group>
          <Text c="dimmed" size="xs">
            The disk is shared by all databases on the MongoDB server. MongoDB{" "}
            {database.mongodb_version}.
          </Text>
        </Stack>
        <Text size="sm">
          Last {growth.days} days: {growth.sweeps} sweeps uploaded, about{" "}
          {formatBytes(growth.bytes)}.{" "}
          {daysUntilFull === null || !fullOn
            ? "No growth to estimate from."
            : daysUntilFull > MAX_FORECAST_DAYS
              ? "At that rate the disk lasts more than 10 years."
              : `At that rate the disk is full in about ${Math.round(daysUntilFull)} days (${fullOn.toLocaleDateString()}).`}
        </Text>
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Collection</Table.Th>
              <Table.Th ta="right">Documents</Table.Th>
              <Table.Th ta="right">Data</Table.Th>
              <Table.Th ta="right">On disk</Table.Th>
              <Table.Th ta="right">Indexes</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {database.collections.map((c) => (
              <Table.Tr key={c.name}>
                <Table.Td>{c.name}</Table.Td>
                <Table.Td ta="right">{c.documents.toLocaleString()}</Table.Td>
                <Table.Td ta="right">{formatBytes(c.data_bytes)}</Table.Td>
                <Table.Td ta="right">{formatBytes(c.storage_bytes)}</Table.Td>
                <Table.Td ta="right">{formatBytes(c.index_bytes)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Stack>
    </Card>
  );
}

function PortalCard({ status }: { status: SystemStatus }) {
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Text fw={600}>Portal</Text>
        <Text size="sm">
          Version {status.version}, environment <b>{status.environment}</b>
        </Text>
      </Stack>
    </Card>
  );
}

/** "grape" -> its filled colour, "gray.2" -> that shade. */
function swatch(color: string): string {
  const [name, shade] = color.split(".");
  return shade ? `var(--mantine-color-${name}-${shade})` : `var(--mantine-color-${name}-filled)`;
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <Group gap={6} wrap="nowrap">
      <ColorSwatch color={swatch(color)} size={12} withShadow={false} />
      <Text size="xs">{label}</Text>
    </Group>
  );
}
