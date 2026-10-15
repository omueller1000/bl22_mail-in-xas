import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Image,
  NumberInput,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import type { MaterialRequest, PlateType } from "../api/client";
import { useCreateRequest, useMaterialRequests, usePlateTypes } from "../api/materials";
import { PageLoader } from "../auth/guards";
import { type Audience, formatDate, REQUEST_STATE } from "../materials/labels";
import { frameRange, PLATE_IMAGES } from "../materials/plates";
import { PlateList } from "../materials/RequestSummary";

/** Users request empty plates and frames (requirements §7). */
export function MaterialsPage() {
  const { data: plateTypes, isPending } = usePlateTypes();

  return (
    <Stack>
      <Title order={2}>Request Materials</Title>
      {isPending || !plateTypes ? <PageLoader /> : <RequestForm plateTypes={plateTypes} />}
      <MyRequests />
    </Stack>
  );
}

function RequestForm({ plateTypes }: { plateTypes: PlateType[] }) {
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [frames, setFrames] = useState<number | string>(1);
  const [comment, setComment] = useState("");
  const create = useCreateRequest();

  const [low, high] = frameRange(plateTypes, quantities);
  const frameCount = typeof frames === "number" ? frames : Number.NaN;
  const framesValid = Number.isInteger(frameCount) && frameCount >= low && frameCount <= high;
  const totalPlates = Object.values(quantities).reduce((sum, n) => sum + n, 0);

  const submit = () =>
    create.mutate(
      {
        plates: plateTypes
          .filter((t) => (quantities[t.id] ?? 0) > 0)
          .map((t) => ({ plate_type: t.id, quantity: quantities[t.id]! })),
        frames: frameCount,
        comment: comment.trim() || null,
      },
      {
        onSuccess: (request) => {
          notifications.show({ color: "green", message: `Request #${request.number} submitted` });
          setQuantities({});
          setFrames(1);
          setComment("");
        },
      },
    );

  return (
    <Card withBorder maw={760}>
      <Stack>
        <Text>
          We ship empty sample plates, frames and screws. Choose how many plates of each type you
          need and how many frames to mount them on.
        </Text>
        <SimpleGrid cols={{ base: 1, xs: 3 }}>
          {plateTypes.map((type) => (
            <Stack key={type.id} gap={4} align="center">
              <Image src={PLATE_IMAGES[type.id]} h={110} w="auto" fit="contain" alt={type.name} />
              <NumberInput
                label={type.name}
                description={
                  type.blocks_other_side ? "Needs a frame of its own" : `${type.positions.length} positions`
                }
                min={0}
                max={200}
                allowDecimal={false}
                value={quantities[type.id] ?? 0}
                onChange={(value) =>
                  setQuantities((q) => ({ ...q, [type.id]: typeof value === "number" ? value : 0 }))
                }
                w={160}
              />
            </Stack>
          ))}
        </SimpleGrid>
        <NumberInput
          label="Frames"
          description={
            totalPlates === 0
              ? "Frames only, without plates"
              : low === high
                ? `Exactly ${low} for these plates`
                : `Between ${low} and ${high} for these plates`
          }
          error={!framesValid && `Choose ${low === high ? low : `${low}–${high}`} frames`}
          min={1}
          max={high}
          allowDecimal={false}
          value={frames}
          onChange={setFrames}
          w={240}
        />
        <Textarea
          label="Comment (optional)"
          autosize
          minRows={2}
          maxLength={1000}
          value={comment}
          onChange={(event) => setComment(event.currentTarget.value)}
        />
        {create.isError && <Alert color="red">{create.error.message}</Alert>}
        <Group justify="flex-end">
          <Button onClick={submit} disabled={!framesValid} loading={create.isPending}>
            Submit request
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

function MyRequests() {
  const { data: requests, isPending, error } = useMaterialRequests();
  if (isPending) return <PageLoader />;
  if (error) return <Alert color="red">{error.message}</Alert>;

  return (
    <Stack gap="xs">
      <Title order={3}>Your requests</Title>
      {requests.length === 0 ? (
        <Text c="dimmed">No requests yet.</Text>
      ) : (
        <Table.ScrollContainer minWidth={640}>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>#</Table.Th>
                <Table.Th>Submitted</Table.Th>
                <Table.Th>Plates</Table.Th>
                <Table.Th>Frames</Table.Th>
                <Table.Th>Status</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {requests.map((request) => (
                <Table.Tr key={request.id}>
                  <Table.Td>{request.number}</Table.Td>
                  <Table.Td>{formatDate(request.created_at)}</Table.Td>
                  <Table.Td>
                    <PlateList request={request} />
                  </Table.Td>
                  <Table.Td>{request.frames}</Table.Td>
                  <Table.Td>
                    <RequestStatus request={request} audience="user" />
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

export function RequestStatus({
  request,
  audience,
}: {
  request: MaterialRequest;
  audience: Audience;
}) {
  const state = REQUEST_STATE[request.state];
  // Users see their frames once shipped; operators as soon as they are issued.
  const showFrames =
    request.state === "fulfilled" || (audience === "operator" && request.state === "issued");
  return (
    <Stack gap={2}>
      <Badge color={state.color} variant="light">
        {state[audience]}
      </Badge>
      {showFrames && (
        <Text size="xs" c="dimmed">
          Frames: {request.barcodes.join(", ")}
        </Text>
      )}
      {request.state === "rejected" && request.reject_reason && (
        <Text size="xs" c="dimmed">
          {request.reject_reason}
        </Text>
      )}
    </Stack>
  );
}
