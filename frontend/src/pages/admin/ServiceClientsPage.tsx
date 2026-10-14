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
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconKey, IconTrash } from "@tabler/icons-react";
import { useState } from "react";

import type { ApiKey, ServiceClient } from "../../api/client";
import {
  useCreateKey,
  useCreateServiceClient,
  useRevokeKey,
  useServiceClients,
} from "../../api/serviceClients";
import { PageLoader } from "../../auth/guards";
import { CopyIcon } from "../../components/CopyIcon";
import { formatDateTime } from "../../materials/labels";

/** Service clients (e.g. the beamline control software) and their API keys (§3.4). */
export function ServiceClientsPage() {
  const { data: clients, isPending, error } = useServiceClients();

  return (
    <Stack>
      <Title order={2}>Service clients</Title>
      <Text size="sm" c="dimmed" maw={720}>
        Programs that use the instrument API, such as the beamline control software. They
        authenticate with an API key. A new key is shown only once; store it in the program's
        configuration right away. Revoke keys that are no longer needed.
      </Text>
      <NewClientForm />
      {isPending ? (
        <PageLoader />
      ) : error ? (
        <Alert color="red">{error.message}</Alert>
      ) : clients.length === 0 ? (
        <Text c="dimmed">No service clients yet.</Text>
      ) : (
        clients.map((client) => <ClientCard key={client.id} client={client} />)
      )}
    </Stack>
  );
}

function NewClientForm() {
  const [name, setName] = useState("");
  const create = useCreateServiceClient();
  return (
    <Group align="flex-end">
      <TextInput
        label="New service client"
        placeholder="e.g. BL22 control software"
        value={name}
        onChange={(event) => setName(event.currentTarget.value)}
        w={320}
      />
      <Button
        disabled={!name.trim()}
        loading={create.isPending}
        onClick={() =>
          create.mutate(name.trim(), {
            onSuccess: () => setName(""),
            onError: (err) => notifications.show({ color: "red", message: err.message }),
          })
        }
      >
        Add
      </Button>
    </Group>
  );
}

function ClientCard({ client }: { client: ServiceClient }) {
  const createKey = useCreateKey();
  const [newKey, setNewKey] = useState<string | null>(null);

  return (
    <Card withBorder maw={900}>
      <Stack gap="sm">
        <Group justify="space-between">
          <div>
            <Text fw={600}>{client.name}</Text>
            <Text size="xs" c="dimmed">
              Added by {client.created_by} on {formatDateTime(client.created_at)}
            </Text>
          </div>
          <Button
            size="xs"
            variant="light"
            leftSection={<IconKey size={14} />}
            loading={createKey.isPending}
            onClick={() =>
              createKey.mutate(client.id, {
                onSuccess: (created) => setNewKey(created.key),
                onError: (err) => notifications.show({ color: "red", message: err.message }),
              })
            }
          >
            New key
          </Button>
        </Group>
        {client.keys.length === 0 ? (
          <Text size="sm" c="dimmed">
            No keys.
          </Text>
        ) : (
          <Table aria-label={`Keys of ${client.name}`}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Key</Table.Th>
                <Table.Th>Created</Table.Th>
                <Table.Th>Last used</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th w={40} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {client.keys.map((key) => (
                <KeyRow key={key.id} clientId={client.id} apiKey={key} />
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Stack>
      <Modal opened={newKey !== null} onClose={() => setNewKey(null)} title="New API key" size="lg">
        <Stack>
          <Alert color="yellow">
            Copy this key now and store it in the program's configuration. It will not be shown
            again.
          </Alert>
          <Group gap="xs" wrap="nowrap">
            <Code block style={{ flex: 1, wordBreak: "break-all" }}>
              {newKey}
            </Code>
            {newKey && <CopyIcon value={newKey} label="API key" />}
          </Group>
          <Group justify="flex-end">
            <Button onClick={() => setNewKey(null)}>Done</Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  );
}

function KeyRow({ clientId, apiKey }: { clientId: string; apiKey: ApiKey }) {
  const revoke = useRevokeKey();
  const [confirming, setConfirming] = useState(false);
  const revoked = apiKey.revoked_at !== null;

  return (
    <Table.Tr c={revoked ? "dimmed" : undefined}>
      <Table.Td ff="monospace">{apiKey.prefix}…</Table.Td>
      <Table.Td>
        <Text size="sm">{formatDateTime(apiKey.created_at)}</Text>
        <Text size="xs" c="dimmed">
          by {apiKey.created_by}
        </Text>
      </Table.Td>
      <Table.Td>{apiKey.last_used_at ? formatDateTime(apiKey.last_used_at) : "never"}</Table.Td>
      <Table.Td>
        {revoked ? (
          <Badge variant="light" color="red">
            Revoked {formatDateTime(apiKey.revoked_at!)}
          </Badge>
        ) : (
          <Badge variant="light" color="green">
            Active
          </Badge>
        )}
      </Table.Td>
      <Table.Td>
        {!revoked && (
          <Tooltip label="Revoke key" withArrow>
            <ActionIcon
              variant="subtle"
              color="red"
              aria-label={`Revoke key ${apiKey.prefix}`}
              onClick={() => setConfirming(true)}
            >
              <IconTrash size={16} />
            </ActionIcon>
          </Tooltip>
        )}
        <Modal opened={confirming} onClose={() => setConfirming(false)} title="Revoke API key">
          <Stack>
            <Text size="sm">
              Revoke key <b>{apiKey.prefix}…</b>? Programs using it lose access immediately. This
              cannot be undone.
            </Text>
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
              <Button
                color="red"
                loading={revoke.isPending}
                onClick={() =>
                  revoke.mutate(
                    { clientId, keyId: apiKey.id },
                    { onSuccess: () => setConfirming(false) },
                  )
                }
              >
                Revoke
              </Button>
            </Group>
          </Stack>
        </Modal>
      </Table.Td>
    </Table.Tr>
  );
}
