import { Alert, Anchor, Badge, Select, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { useMe } from "../api/auth";
import type { Role, User } from "../api/client";
import { useSetRole, useUsers } from "../api/users";
import { PageLoader } from "../auth/guards";
import { hasRole, ROLE_LABELS, ROLES } from "../auth/roles";

/** User list for Operators; Admins can also change roles. */
export function UsersPage() {
  const { data: me } = useMe();
  const { data: users, isPending, error } = useUsers();
  const [filter, setFilter] = useState("");

  if (isPending) return <PageLoader />;
  if (error) return <Alert color="red">{error.message}</Alert>;

  const isAdmin = me?.user ? hasRole(me.user.role, "admin") : false;
  const needle = filter.trim().toLowerCase();
  const shown = users.filter((u) =>
    [u.name, u.orcid, u.email, u.affiliation].some((field) => field.toLowerCase().includes(needle)),
  );

  return (
    <Stack>
      <Title order={2}>All Users</Title>
      <TextInput
        placeholder="Filter by name, ORCID iD, email or affiliation"
        value={filter}
        onChange={(event) => setFilter(event.currentTarget.value)}
        maw={420}
      />
      <Table.ScrollContainer minWidth={800}>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>ORCID iD</Table.Th>
              <Table.Th>Affiliation</Table.Th>
              <Table.Th>Email / phone</Table.Th>
              <Table.Th>Role</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {shown.map((user) => (
              <Table.Tr key={user.id}>
                <Table.Td>{user.name}</Table.Td>
                <Table.Td>
                  <Anchor href={`https://orcid.org/${user.orcid}`} target="_blank" rel="noreferrer">
                    {user.orcid}
                  </Anchor>
                </Table.Td>
                <Table.Td>{user.affiliation}</Table.Td>
                <Table.Td>
                  <Text size="sm">{user.email}</Text>
                  <Text size="sm" c="dimmed">
                    {user.phone}
                  </Text>
                </Table.Td>
                <Table.Td>
                  {isAdmin && user.id !== me?.user?.id ? (
                    <RoleSelect user={user} />
                  ) : (
                    <Badge variant="light">{ROLE_LABELS[user.role]}</Badge>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {shown.length === 0 && <Text c="dimmed">No users match.</Text>}
    </Stack>
  );
}

function RoleSelect({ user }: { user: User }) {
  const setRole = useSetRole();
  return (
    <Select
      aria-label={`Role of ${user.name}`}
      data={ROLES.map((role) => ({ value: role, label: ROLE_LABELS[role] }))}
      value={user.role}
      allowDeselect={false}
      disabled={setRole.isPending}
      w={140}
      onChange={(value) => {
        if (!value || value === user.role) return;
        setRole.mutate(
          { userId: user.id, role: value as Role },
          {
            onSuccess: (updated) =>
              notifications.show({
                color: "green",
                message: `${updated.name} is now ${ROLE_LABELS[updated.role]}`,
              }),
            onError: (err) => notifications.show({ color: "red", message: err.message }),
          },
        );
      }}
    />
  );
}
