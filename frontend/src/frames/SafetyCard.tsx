import { Alert, Badge, Button, Card, Checkbox, Group, List, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconLock, IconLockOpen, IconShieldCheck } from "@tabler/icons-react";
import { useState } from "react";

import type { Frame } from "../api/client";
import { useDeclareSafe, useSetLocked } from "../api/measurements";
import { formatDate } from "../materials/labels";

const SAFETY_STATEMENT =
  "I declare that all samples on this frame are solid and non-hazardous.";

const DECLARABLE_STATES = ["issued", "shipped_to_user", "received_on_hold"];
const NO_UNLOCK_STATES = ["scheduled", "loaded", "returned", "void"];

/** Safety declaration (owner only) and lock (owner or Operator), requirements §6.4. */
export function SafetyCard({ frame, isOwner }: { frame: Frame; isOwner: boolean }) {
  const [confirmed, setConfirmed] = useState(false);
  const declare = useDeclareSafe(frame);
  const setLocked = useSetLocked(frame);
  const fail = (err: Error) => notifications.show({ color: "red", message: err.message });

  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={600}>Safety and lock</Text>

        {frame.missing.length > 0 && (
          <Alert color="yellow" title="Before declaring the frame safe">
            <List size="sm">
              {frame.missing.map((item) => (
                <List.Item key={item}>{item}</List.Item>
              ))}
            </List>
          </Alert>
        )}

        {frame.safety ? (
          <Group gap="xs">
            <IconShieldCheck size={18} color="var(--mantine-color-green-6)" />
            <Text size="sm">
              Declared safe by {frame.safety.by} on {formatDate(frame.safety.at)}.
            </Text>
          </Group>
        ) : isOwner && DECLARABLE_STATES.includes(frame.state) ? (
          <Stack gap="xs">
            <Checkbox
              label={SAFETY_STATEMENT}
              checked={confirmed}
              onChange={(event) => setConfirmed(event.currentTarget.checked)}
            />
            <Text size="xs" c="dimmed">
              This cannot be undone: afterwards plates and samples can no longer change.
              Measurements stay editable until the frame is locked.
            </Text>
            <Group justify="flex-end">
              <Button
                disabled={!confirmed || frame.missing.length > 0}
                loading={declare.isPending}
                onClick={() => declare.mutate(undefined, { onError: fail })}
              >
                Declare safe
              </Button>
            </Group>
          </Stack>
        ) : (
          <Text size="sm" c="dimmed">
            Not yet declared safe{isOwner ? "" : " (only the owner can declare it)"}.
          </Text>
        )}

        {frame.safety && (
          <Group justify="space-between">
            <Group gap="xs">
              {frame.locked ? <IconLock size={18} /> : <IconLockOpen size={18} />}
              <Badge variant="light" color={frame.locked ? "blue" : "gray"}>
                {frame.locked ? "Locked" : "Unlocked"}
              </Badge>
              <Text size="xs" c="dimmed">
                {frame.locked
                  ? "Measurements are final; unlock to change them."
                  : "Lock the frame when its measurements are final."}
              </Text>
            </Group>
            {frame.locked ? (
              <Button
                variant="default"
                disabled={NO_UNLOCK_STATES.includes(frame.state)}
                loading={setLocked.isPending}
                onClick={() => setLocked.mutate(false, { onError: fail })}
              >
                Unlock
              </Button>
            ) : (
              <Button
                disabled={frame.missing.length > 0}
                loading={setLocked.isPending}
                onClick={() => setLocked.mutate(true, { onError: fail })}
              >
                Lock
              </Button>
            )}
          </Group>
        )}
      </Stack>
    </Card>
  );
}
