import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { Fragment, useState } from "react";

import type { PlateType, ShippingGroup } from "../../api/client";
import { useMarkShipped, usePlateTypes, useShippingList } from "../../api/materials";
import { PageLoader } from "../../auth/guards";
import { CopyIcon } from "../../components/CopyIcon";
import { plateSummary } from "../../frames/summary";

/** Everything to be shipped, one box per user: new material and returning frames (§9.3). */
export function ShippingPage() {
  const { data: groups, isPending, error } = useShippingList();
  const { data: plateTypes = [] } = usePlateTypes();

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
            <GroupCard key={group.user.id} group={group} plateTypes={plateTypes} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}

/** All barcodes in a box: everything ships together. */
function barcodesOf(group: ShippingGroup): string[] {
  return [
    ...group.requests.flatMap((r) => r.barcodes),
    ...group.returning.map((f) => f.barcode),
  ];
}

function GroupCard({ group, plateTypes }: { group: ShippingGroup; plateTypes: PlateType[] }) {
  const [confirming, setConfirming] = useState(false);
  const ship = useMarkShipped();
  const { user } = group;
  const barcodes = barcodesOf(group);
  const plateName = (id: string) => plateTypes.find((t) => t.id === id)?.name ?? id;

  return (
    <Card withBorder>
      <Stack gap="xs">
        <ShippingDetails user={user} />
        <Table mt="xs" aria-label={`Shipment to ${user.name}`}>
          <Table.Tbody>
            {group.requests.map((request) => (
              <Fragment key={request.id ?? "frames"}>
                <Table.Tr bg="var(--mantine-color-default-hover)">
                  <Table.Td colSpan={2} fw={600}>
                    {request.number ? `Material request #${request.number}` : "New frames"}
                  </Table.Td>
                </Table.Tr>
                {request.plates.length > 0 && (
                  <Table.Tr>
                    <Table.Td w={110}>Plates</Table.Td>
                    <Table.Td>
                      {request.plates
                        .map((p) => `${p.quantity} × ${plateName(p.plate_type)}`)
                        .join(", ")}
                    </Table.Td>
                  </Table.Tr>
                )}
                <Table.Tr>
                  <Table.Td w={110}>
                    {request.barcodes.length} frame{request.barcodes.length !== 1 && "s"}
                  </Table.Td>
                  <Table.Td ff="monospace">{request.barcodes.join("  ")}</Table.Td>
                </Table.Tr>
              </Fragment>
            ))}
            {group.returning.length > 0 && (
              <>
                <Table.Tr bg="var(--mantine-color-default-hover)">
                  <Table.Td colSpan={2} fw={600}>
                    Returning frames ({group.returning.length})
                  </Table.Td>
                </Table.Tr>
                {group.returning.map((frame) => (
                  <Table.Tr key={frame.barcode}>
                    <Table.Td w={110} ff="monospace">
                      {frame.barcode}
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs" justify="space-between" wrap="nowrap">
                        <Text size="sm">{plateSummary(frame, plateTypes)}</Text>
                        <MeasuredStatus measurements={frame.measurements} />
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </>
            )}
          </Table.Tbody>
        </Table>
        <Group justify="flex-end">
          <Button onClick={() => setConfirming(true)}>Mark shipped</Button>
        </Group>
      </Stack>
      <Modal opened={confirming} onClose={() => setConfirming(false)} title="Mark as shipped">
        <Stack>
          <Text>
            Mark everything in this box for {user.name} as shipped ({barcodes.length} frame
            {barcodes.length !== 1 && "s"})? {user.name} gets one email listing the shipment.
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

/** "measured", "2 failed", "3 of 5 measured" or "not measured" (e.g. returned from hold). */
function MeasuredStatus({
  measurements: { done, error, pending },
}: {
  measurements: ShippingGroup["returning"][number]["measurements"];
}) {
  const total = done + error + pending;
  if (error > 0) {
    return (
      <Badge variant="light" color="red">
        {error} failed
      </Badge>
    );
  }
  if (total > 0 && done === total) {
    return (
      <Badge variant="light" color="green">
        measured
      </Badge>
    );
  }
  if (done > 0) {
    return (
      <Badge variant="light" color="yellow">
        {done} of {total} measured
      </Badge>
    );
  }
  return (
    <Badge variant="light" color="gray">
      not measured
    </Badge>
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
