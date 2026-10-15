import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Modal,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconEye } from "@tabler/icons-react";
import { useState } from "react";

import type { components } from "../../api/schema";
import { useMailStatus, useOutbox, useSendTestEmail, useSetMailSwitches } from "../../api/mail";
import { PageLoader } from "../../auth/guards";
import { formatDateTime } from "../../materials/labels";

type MailStatus = components["schemas"]["MailStatus"];
type OutboxEmail = components["schemas"]["OutboxEmail"];

// Colour convention: green done, blue normal (waiting), red failed, yellow warning.
const STATUS_COLORS: Record<string, string> = {
  sent: "green",
  queued: "blue",
  collecting: "blue",
  sending: "indigo",
  failed: "red",
  suppressed: "yellow",
  not_sent: "gray",
};

const KIND_LABELS: Record<string, string> = {
  email_code: "Confirmation code",
  material_request: "Material request",
  shipped: "Shipped",
  arrived: "Arrived",
  on_hold: "On hold",
  on_hold_staff: "On hold (staff)",
  frame_complete: "Frame complete",
  frame_complete_staff: "Frame complete (staff)",
  returned: "Returned",
  test: "Test",
};

/** Notification emails: switch them off, redirect them, see what was sent (§6.8). */
export function EmailPage() {
  const { data: status, isPending, error } = useMailStatus();

  return (
    <Stack>
      <Title order={2}>Email</Title>
      <Text c="dimmed" size="sm">
        Notification emails to users and operators. Confirmation codes are always sent to the
        address being confirmed.
      </Text>
      {isPending ? (
        <PageLoader />
      ) : error ? (
        <Alert color="red">{error.message}</Alert>
      ) : (
        <>
          <ServerCard status={status} />
          <SwitchesCard key={JSON.stringify(status.switches)} status={status} />
          <TestCard />
          <OutboxCard />
        </>
      )}
    </Stack>
  );
}

function ServerCard({ status }: { status: MailStatus }) {
  const production = status.environment === "prod";
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Text fw={600}>Server</Text>
        {!status.configured && (
          <Alert color="red">
            Mail is not configured: the server needs an SMTP host and a sender address
            (HT_XAS_SMTP_HOST, HT_XAS_MAIL_FROM_ADDRESS). Nothing can be sent.
          </Alert>
        )}
        {!production && (
          <Alert color="yellow">
            Environment <b>{status.environment}</b>: emails never reach their recipients.{" "}
            {status.dev_redirect
              ? `All emails go to ${status.dev_redirect}.`
              : "They are only recorded below (no HT_XAS_MAIL_DEV_REDIRECT set)."}
          </Alert>
        )}
        <Text size="sm">
          Sender: <b>BL22</b> &lt;{status.from_address ?? "not set"}&gt;
        </Text>
      </Stack>
    </Card>
  );
}

function SwitchesCard({ status }: { status: MailStatus }) {
  const save = useSetMailSwitches();
  const [enabled, setEnabled] = useState(status.switches.enabled);
  const [redirect, setRedirect] = useState(status.switches.redirect_to ?? "");
  const edited =
    enabled !== status.switches.enabled || redirect.trim() !== (status.switches.redirect_to ?? "");

  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={600}>Notifications</Text>
        <Switch
          label="Send notification emails"
          description="Off: no notification is sent to anyone (they are recorded as suppressed)."
          checked={enabled}
          onChange={(e) => setEnabled(e.currentTarget.checked)}
        />
        <TextInput
          label="Redirect all notifications to"
          description="For troubleshooting: every notification goes to this address instead of its recipients. Leave empty to send normally."
          placeholder="name@example.org"
          value={redirect}
          onChange={(e) => setRedirect(e.currentTarget.value)}
          maw={420}
        />
        {!status.switches.enabled && (
          <Alert color="yellow">Notification emails are switched off.</Alert>
        )}
        {status.switches.enabled && status.switches.redirect_to && (
          <Alert color="yellow">
            All notifications go to {status.switches.redirect_to}, not to their recipients.
          </Alert>
        )}
        <Group>
          <Button
            disabled={!edited}
            loading={save.isPending}
            onClick={() =>
              save.mutate(
                { enabled, redirect_to: redirect.trim() || null },
                {
                  onSuccess: () => notifications.show({ color: "green", message: "Saved" }),
                  onError: (e) => notifications.show({ color: "red", message: e.message }),
                },
              )
            }
          >
            Save
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

function TestCard() {
  const send = useSendTestEmail();
  const [to, setTo] = useState("");
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={600}>Test email</Text>
        <Group align="end">
          <TextInput
            label="Send a test email to"
            placeholder="name@example.org"
            value={to}
            onChange={(e) => setTo(e.currentTarget.value)}
            w={300}
          />
          <Button
            variant="light"
            disabled={!to.includes("@")}
            loading={send.isPending}
            onClick={() =>
              send.mutate(to.trim(), {
                onSuccess: () =>
                  notifications.show({
                    color: "green",
                    message: "Test email queued; its status appears below",
                  }),
                onError: (e) => notifications.show({ color: "red", message: e.message }),
              })
            }
          >
            Send
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

function OutboxCard() {
  const { data: emails = [], isPending } = useOutbox();
  const [shown, setShown] = useState<OutboxEmail | null>(null);
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={600}>Recent emails</Text>
        {isPending ? (
          <PageLoader />
        ) : emails.length === 0 ? (
          <Text c="dimmed" size="sm">
            No emails yet.
          </Text>
        ) : (
          <Table.ScrollContainer minWidth={800}>
            <Table striped verticalSpacing={4} fz="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Created</Table.Th>
                  <Table.Th>Kind</Table.Th>
                  <Table.Th>To</Table.Th>
                  <Table.Th>Subject</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th w={40} />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {emails.map((email) => (
                  <Table.Tr key={email.id}>
                    <Table.Td>{formatDateTime(email.created_at)}</Table.Td>
                    <Table.Td>{KIND_LABELS[email.kind] ?? email.kind}</Table.Td>
                    <Table.Td>
                      <Text size="sm" lineClamp={2}>
                        {email.to.join(", ")}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" lineClamp={2}>
                        {email.subject ?? "—"}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Tooltip
                        label={describe(email)}
                        disabled={!describe(email)}
                        multiline
                        w={320}
                        withArrow
                      >
                        <Badge color={STATUS_COLORS[email.status] ?? "gray"} variant="light">
                          {email.status.replace("_", " ")}
                        </Badge>
                      </Tooltip>
                    </Table.Td>
                    <Table.Td>
                      {email.text && (
                        <ActionIcon
                          variant="subtle"
                          aria-label={`Show email ${email.subject ?? ""}`}
                          onClick={() => setShown(email)}
                        >
                          <IconEye size={16} />
                        </ActionIcon>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Stack>
      <Modal opened={shown !== null} onClose={() => setShown(null)} title={shown?.subject} size="lg">
        <Code block>{shown?.text}</Code>
      </Modal>
    </Card>
  );
}

function describe(email: OutboxEmail): string {
  const parts = [];
  if (email.status === "collecting")
    parts.push(`Collecting arrivals; sent at ${formatDateTime(email.send_after)}`);
  if (email.sent_at) parts.push(`Sent ${formatDateTime(email.sent_at)}`);
  if (email.delivered_to && email.delivered_to.join() !== email.to.join())
    parts.push(`delivered to ${email.delivered_to.join(", ")}`);
  if (email.attempts) parts.push(`${email.attempts} attempt(s)`);
  if (email.error) parts.push(email.error);
  return parts.join(" · ");
}
