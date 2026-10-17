import { Group, SegmentedControl, Stack, TextInput, Title } from "@mantine/core";
import { IconSearch } from "@tabler/icons-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import type { MaterialRequest, RequestState } from "../../api/client";
import { useAllMaterialRequests } from "../../api/materials";
import { type PagedColumn, PagedTable } from "../../components/PagedTable";
import { usePaging } from "../../components/paging";
import { formatDate } from "../../materials/labels";
import { PlateList } from "../../materials/RequestSummary";
import { RequestStatus } from "../MaterialsPage";

type Filter = RequestState | "all";

/** All users' material requests, paged on the server; open ones first (requirements §9.5). */
export function RequestsPage() {
  const [filter, setFilter] = useState<Filter>("submitted");
  const paging = usePaging<"number">({ sort: "number", order: "desc" });
  const requests = useAllMaterialRequests({
    ...paging.params,
    state: filter === "all" ? undefined : filter,
  });
  const navigate = useNavigate();

  const columns: PagedColumn<MaterialRequest, "number">[] = [
    { key: "number", label: "#", sort: "number", render: (request) => request.number },
    { key: "user", label: "User", render: (request) => request.user.name },
    { key: "submitted", label: "Submitted", render: (request) => formatDate(request.created_at) },
    { key: "plates", label: "Plates", render: (request) => <PlateList request={request} /> },
    { key: "frames", label: "Frames", render: (request) => request.frames },
    {
      key: "status",
      label: "Status",
      render: (request) => <RequestStatus request={request} audience="operator" />,
    },
  ];

  return (
    <Stack>
      <Title order={2}>Material Requests</Title>
      <Group>
        <SegmentedControl
          value={filter}
          onChange={(value) => {
            setFilter(value as Filter);
            paging.firstPage();
          }}
          data={[
            { value: "submitted", label: "Open" },
            { value: "issued", label: "Issued" },
            { value: "fulfilled", label: "Fulfilled" },
            { value: "rejected", label: "Rejected" },
            { value: "all", label: "All" },
          ]}
          w="fit-content"
        />
        <TextInput
          aria-label="Search requests"
          placeholder="Request number or user"
          leftSection={<IconSearch size={16} />}
          value={paging.search}
          onChange={(event) => paging.setSearch(event.currentTarget.value)}
          w={260}
        />
      </Group>
      <PagedTable
        columns={columns}
        paging={paging}
        query={requests}
        rowKey={(request) => request.id}
        onRowClick={(request) => navigate(`/operator/requests/${request.id}`)}
        minWidth={760}
        empty="No requests."
      />
    </Stack>
  );
}
