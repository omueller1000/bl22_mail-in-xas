import { Alert, SegmentedControl, Stack, Table, Text, Title } from "@mantine/core";
import { useState } from "react";
import { useNavigate } from "react-router";

import type { RequestState } from "../../api/client";
import { useMaterialRequests } from "../../api/materials";
import { PageLoader } from "../../auth/guards";
import { formatDate } from "../../materials/labels";
import { PlateList } from "../../materials/RequestSummary";
import { RequestStatus } from "../MaterialsPage";

type Filter = RequestState | "all";

/** All users' material requests; open ones first (requirements §9.5). */
export function RequestsPage() {
  const [filter, setFilter] = useState<Filter>("submitted");
  const { data: requests, isPending, error } = useMaterialRequests({
    allUsers: true,
    state: filter === "all" ? undefined : filter,
  });
  const navigate = useNavigate();

  return (
    <Stack>
      <Title order={2}>Material requests</Title>
      <SegmentedControl
        value={filter}
        onChange={(value) => setFilter(value as Filter)}
        data={[
          { value: "submitted", label: "Open" },
          { value: "issued", label: "Issued" },
          { value: "fulfilled", label: "Fulfilled" },
          { value: "rejected", label: "Rejected" },
          { value: "all", label: "All" },
        ]}
        w="fit-content"
      />
      {isPending ? (
        <PageLoader />
      ) : error ? (
        <Alert color="red">{error.message}</Alert>
      ) : requests.length === 0 ? (
        <Text c="dimmed">No requests.</Text>
      ) : (
        <Table.ScrollContainer minWidth={760}>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>#</Table.Th>
                <Table.Th>User</Table.Th>
                <Table.Th>Submitted</Table.Th>
                <Table.Th>Plates</Table.Th>
                <Table.Th>Frames</Table.Th>
                <Table.Th>Status</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {requests.map((request) => (
                <Table.Tr
                  key={request.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate(`/operator/requests/${request.id}`)}
                >
                  <Table.Td>{request.number}</Table.Td>
                  <Table.Td>{request.user.name}</Table.Td>
                  <Table.Td>{formatDate(request.created_at)}</Table.Td>
                  <Table.Td>
                    <PlateList request={request} />
                  </Table.Td>
                  <Table.Td>{request.frames}</Table.Td>
                  <Table.Td>
                    <RequestStatus request={request} audience="operator" />
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
