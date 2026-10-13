import { Badge, Card, Group, Loader, Stack, Text, Title } from "@mantine/core";

import { useHealth } from "../api/health";

export function HomePage() {
  return (
    <Stack maw={640}>
      <Title order={2}>Welcome</Title>
      <Text>
        Request sample frames, define samples and measurements, and view your XAS data from the
        BL22 high-throughput mail-in program.
      </Text>
      <SystemStatus />
    </Stack>
  );
}

function SystemStatus() {
  const { data, isPending, isError } = useHealth();

  return (
    <Card withBorder>
      <Text fw={600} mb="xs">
        System status
      </Text>
      {isPending ? (
        <Loader size="sm" />
      ) : isError ? (
        <StatusRow label="Server" ok={false} text="unreachable" />
      ) : (
        <Stack gap={4}>
          <StatusRow label="Server" ok text={`v${data.version} (${data.environment})`} />
          <StatusRow label="Database" ok={data.database === "ok"} text={data.database} />
        </Stack>
      )}
    </Card>
  );
}

function StatusRow({ label, ok, text }: { label: string; ok: boolean; text: string }) {
  return (
    <Group gap="xs">
      <Text w={80}>{label}</Text>
      <Badge color={ok ? "green" : "red"} variant="light">
        {text}
      </Badge>
    </Group>
  );
}
