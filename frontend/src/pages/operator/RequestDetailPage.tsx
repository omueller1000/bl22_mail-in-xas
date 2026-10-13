import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Stack,
  Table,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useParams } from "react-router";

import type { MaterialRequest } from "../../api/client";
import {
  fetchFrame,
  useIssueBarcodes,
  useMaterialRequest,
  useRejectRequest,
} from "../../api/materials";
import { PageLoader } from "../../auth/guards";
import { CopyIcon } from "../../components/CopyIcon";
import { ScanInput } from "../../components/ScanInput";
import { FRAME_STATE_LABELS, formatDate } from "../../materials/labels";
import { PlateList } from "../../materials/RequestSummary";
import { RequestStatus } from "../MaterialsPage";

export function RequestDetailPage() {
  const { requestId = "" } = useParams();
  const { data: request, isPending, error } = useMaterialRequest(requestId);

  if (isPending) return <PageLoader />;
  if (error) return <Alert color="red">{error.message}</Alert>;

  return (
    <Stack>
      <Anchor component={Link} to="/operator/requests" size="sm">
        ← All requests
      </Anchor>
      <Title order={2}>Request #{request.number}</Title>
      <Card withBorder maw={640}>
        <Table variant="vertical">
          <Table.Tbody>
            <Table.Tr>
              <Table.Th w={140}>User</Table.Th>
              <Table.Td>{request.user.name}</Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Th>Email</Table.Th>
              <Table.Td>
                <Group gap="xs" wrap="nowrap">
                  <Anchor href={`mailto:${request.user.email}`}>{request.user.email}</Anchor>
                  <CopyIcon value={request.user.email} label="email" />
                </Group>
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Th>Submitted</Table.Th>
              <Table.Td>{formatDate(request.created_at)}</Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Th>Plates</Table.Th>
              <Table.Td>
                <PlateList request={request} />
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Th>Frames</Table.Th>
              <Table.Td>{request.frames}</Table.Td>
            </Table.Tr>
            {request.comment && (
              <Table.Tr>
                <Table.Th>Comment</Table.Th>
                <Table.Td style={{ whiteSpace: "pre-wrap" }}>{request.comment}</Table.Td>
              </Table.Tr>
            )}
            <Table.Tr>
              <Table.Th>Status</Table.Th>
              <Table.Td>
                <RequestStatus request={request} audience="operator" />
                {request.decided_by && (
                  <Text size="xs" c="dimmed">
                    by {request.decided_by}
                  </Text>
                )}
              </Table.Td>
            </Table.Tr>
          </Table.Tbody>
        </Table>
      </Card>
      {request.state === "submitted" && <IssuePanel request={request} />}
    </Stack>
  );
}

interface Scanned {
  barcode: string;
  status: "checking" | "ok" | "error";
  message: string;
}

/** Scan exactly `frames` reserved barcodes, then issue them to the user (all or nothing). */
function IssuePanel({ request }: { request: MaterialRequest }) {
  const [scanned, setScanned] = useState<Scanned[]>([]);
  const [rejecting, setRejecting] = useState(false);
  const issue = useIssueBarcodes();

  const update = (barcode: string, change: Partial<Scanned>) =>
    setScanned((rows) => rows.map((row) => (row.barcode === barcode ? { ...row, ...change } : row)));

  const onScan = (barcode: string) => {
    if (scanned.some((row) => row.barcode === barcode)) {
      notifications.show({ color: "yellow", message: `${barcode} is already in the list` });
      return;
    }
    setScanned((rows) => [...rows, { barcode, status: "checking", message: "Checking…" }]);
    fetchFrame(barcode)
      .then((frame) => {
        if (!frame) update(barcode, { status: "error", message: "Unknown barcode" });
        else if (frame.state !== "reserved")
          update(barcode, { status: "error", message: `Already ${FRAME_STATE_LABELS[frame.state]}` });
        else update(barcode, { status: "ok", message: "Reserved" });
      })
      .catch((err: Error) => update(barcode, { status: "error", message: err.message }));
  };

  const okCount = scanned.filter((row) => row.status === "ok").length;
  const ready = okCount === request.frames && scanned.length === request.frames;

  return (
    <Card withBorder maw={640}>
      <Stack>
        <Title order={4}>Issue frames</Title>
        <Text size="sm">
          Scan the labels of {request.frames} reserved frame{request.frames > 1 && "s"} to issue to{" "}
          {request.user.name}.
        </Text>
        <ScanInput onScan={onScan} disabled={issue.isPending} />
        {scanned.length > 0 && (
          <Table>
            <Table.Tbody>
              {scanned.map((row) => (
                <Table.Tr key={row.barcode} bg={row.status === "error" ? "red.1" : undefined}>
                  <Table.Td ff="monospace">{row.barcode}</Table.Td>
                  <Table.Td>
                    <Badge
                      variant="light"
                      color={row.status === "ok" ? "green" : row.status === "error" ? "red" : "gray"}
                    >
                      {row.message}
                    </Badge>
                  </Table.Td>
                  <Table.Td w={40}>
                    <ActionIcon
                      variant="subtle"
                      color="gray"
                      aria-label={`Remove ${row.barcode}`}
                      onClick={() => setScanned((rows) => rows.filter((r) => r !== row))}
                    >
                      ✕
                    </ActionIcon>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
        <Text size="sm" c={scanned.length > request.frames ? "red" : "dimmed"}>
          {okCount} of {request.frames} ready
          {scanned.length > request.frames && ` — remove ${scanned.length - request.frames}`}
        </Text>
        {issue.isError && <Alert color="red">{issue.error.message}</Alert>}
        <Group justify="space-between">
          <Button variant="subtle" color="red" onClick={() => setRejecting(true)}>
            Reject request…
          </Button>
          <Button
            disabled={!ready}
            loading={issue.isPending}
            onClick={() =>
              issue.mutate(
                { id: request.id, barcodes: scanned.map((row) => row.barcode) },
                {
                  onSuccess: () =>
                    notifications.show({
                      color: "green",
                      message: `${request.frames} frame(s) issued to ${request.user.name}`,
                    }),
                },
              )
            }
          >
            Issue {request.frames} frame{request.frames > 1 && "s"}
          </Button>
        </Group>
      </Stack>
      <RejectModal request={request} opened={rejecting} onClose={() => setRejecting(false)} />
    </Card>
  );
}

function RejectModal({
  request,
  opened,
  onClose,
}: {
  request: MaterialRequest;
  opened: boolean;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const reject = useRejectRequest();
  return (
    <Modal opened={opened} onClose={onClose} title={`Reject request #${request.number}`}>
      <Stack>
        <Textarea
          label="Reason (shown to the user)"
          autosize
          minRows={2}
          maxLength={1000}
          value={reason}
          onChange={(event) => setReason(event.currentTarget.value)}
        />
        {reject.isError && <Alert color="red">{reject.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button
            color="red"
            loading={reject.isPending}
            onClick={() =>
              reject.mutate(
                { id: request.id, reason: reason.trim() || null },
                { onSuccess: onClose },
              )
            }
          >
            Reject
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
