import { Alert, Button, Card, Group, Modal, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import type { ShippingGroup } from "../../api/client";
import { useMarkShipped, useShippingList } from "../../api/materials";
import { PageLoader } from "../../auth/guards";
import { CopyIcon } from "../../components/CopyIcon";

/** Frames issued but not yet shipped, grouped by user (requirements §9.3). */
export function ShippingPage() {
  const { data: groups, isPending, error } = useShippingList();

  return (
    <Stack>
      <Title order={2}>Ready to ship</Title>
      {isPending ? (
        <PageLoader />
      ) : error ? (
        <Alert color="red">{error.message}</Alert>
      ) : groups.length === 0 ? (
        <Text c="dimmed">Nothing to ship.</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {groups.map((group) => (
            <GroupCard key={group.user.id} group={group} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}

function GroupCard({ group }: { group: ShippingGroup }) {
  const [confirming, setConfirming] = useState(false);
  const ship = useMarkShipped();
  const { user, barcodes } = group;
  const n = barcodes.length;

  return (
    <Card withBorder>
      <Stack gap="xs">
        <ShippingDetails user={user} />
        <Text size="sm" fw={600} mt="xs">
          {n} frame{n > 1 && "s"}
        </Text>
        <Text ff="monospace" size="sm">
          {barcodes.join("  ")}
        </Text>
        <Group justify="flex-end">
          <Button onClick={() => setConfirming(true)}>Mark shipped</Button>
        </Group>
      </Stack>
      <Modal opened={confirming} onClose={() => setConfirming(false)} title="Mark as shipped">
        <Stack>
          <Text>
            Mark {n} frame{n > 1 && "s"} for {user.name} as shipped?
          </Text>
          {ship.isError && <Alert color="red">{ship.error.message}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              loading={ship.isPending}
              onClick={() =>
                ship.mutate(barcodes, {
                  onSuccess: () => {
                    setConfirming(false);
                    notifications.show({ color: "green", message: `Shipped to ${user.name}` });
                  },
                })
              }
            >
              Mark shipped
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  );
}

/** The user's shipping details, one value per row, each with a copy button. */
function ShippingDetails({ user }: { user: ShippingGroup["user"] }) {
  const address = user.shipping_address;
  const rows: [string, string | null | undefined][] = [
    ["Name", user.name],
    ["c/o", address.care_of],
    ["Affiliation", user.affiliation],
    ["Street", address.street1],
    ["Street (line 2)", address.street2],
    ["City", address.city],
    ["State / province", address.region],
    ["Postal code", address.postal_code],
    ["Country", address.country],
    ["Phone", user.phone],
    ["Email", user.email],
  ];

  return (
    <Table variant="vertical" withTableBorder layout="fixed">
      <Table.Tbody>
        {rows
          .filter((row): row is [string, string] => Boolean(row[1]))
          .map(([label, value]) => (
            <Table.Tr key={label}>
              <Table.Th w={140}>{label}</Table.Th>
              <Table.Td>
                <Group gap="xs" wrap="nowrap" justify="space-between">
                  <Text size="sm" style={{ overflowWrap: "anywhere" }}>
                    {value}
                  </Text>
                  <CopyIcon value={value} label={label} />
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
      </Table.Tbody>
    </Table>
  );
}
