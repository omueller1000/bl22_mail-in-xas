import { Alert, Anchor, Group, Stack, Text } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { Link } from "react-router";

import { useWarnings } from "../api/scanning";

/**
 * Frames at the facility that need attention (requirements §6.7): on hold because not declared
 * safe, or not locked. Users see their own; Operators see everyone's.
 */
export function WarningsCard({ allUsers = false }: { allUsers?: boolean }) {
  const { data: warnings = [] } = useWarnings(allUsers);
  if (warnings.length === 0) return null;

  return (
    <Alert
      color="yellow"
      icon={<IconAlertTriangle size={18} />}
      title={allUsers ? "Frames needing attention" : "Your frames need attention"}
    >
      <Stack gap={4}>
        {warnings.map((w) => (
          <Group key={w.barcode} gap="xs" wrap="nowrap" align="flex-start">
            <Anchor component={Link} to={`/frames/${w.barcode}`} ff="monospace" size="sm">
              {w.barcode}
            </Anchor>
            {allUsers && w.owner && (
              <Text size="sm" fw={500}>
                {w.owner.name}
              </Text>
            )}
            <Text size="sm">{w.message}</Text>
          </Group>
        ))}
      </Stack>
    </Alert>
  );
}
