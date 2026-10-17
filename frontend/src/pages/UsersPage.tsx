import { Anchor, Badge, Group, Select, Stack, Text, TextInput, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconSearch } from "@tabler/icons-react";
import { useState } from "react";

import { useMe } from "../api/auth";
import type { Role, User } from "../api/client";
import { type UserSort, useSetRole, useUsers } from "../api/users";
import { hasRole, ROLE_LABELS, ROLES } from "../auth/roles";
import { type PagedColumn, PagedTable } from "../components/PagedTable";
import { usePaging } from "../components/paging";

/** User list for Operators, paged on the server; Admins can also change roles. */
export function UsersPage() {
  const { data: me } = useMe();
  const [role, setRole] = useState<Role | null>(null);
  const paging = usePaging<UserSort>({ sort: "name", order: "asc" });
  const users = useUsers({ ...paging.params, role: role ?? undefined });
  const isAdmin = me?.user ? hasRole(me.user.role, "admin") : false;

  const columns: PagedColumn<User, UserSort>[] = [
    { key: "name", label: "Name", sort: "name", render: (user) => user.name },
    {
      key: "orcid",
      label: "ORCID iD",
      render: (user) => (
        <Anchor href={`https://orcid.org/${user.orcid}`} target="_blank" rel="noreferrer">
          {user.orcid}
        </Anchor>
      ),
    },
    { key: "affiliation", label: "Affiliation", sort: "affiliation", render: (user) => user.affiliation },
    {
      key: "contact",
      label: "Email / phone",
      render: (user) => (
        <>
          <Text size="sm">{user.email}</Text>
          <Text size="sm" c="dimmed">
            {user.phone}
          </Text>
        </>
      ),
    },
    {
      key: "role",
      label: "Role",
      render: (user) =>
        isAdmin && user.id !== me?.user?.id ? (
          <RoleSelect user={user} />
        ) : (
          <Badge variant="light">{ROLE_LABELS[user.role]}</Badge>
        ),
    },
  ];

  return (
    <Stack>
      <Title order={2}>All Users</Title>
      <Group>
        <TextInput
          aria-label="Search users"
          placeholder="Search by name, ORCID iD, email or affiliation"
          leftSection={<IconSearch size={16} />}
          value={paging.search}
          onChange={(event) => paging.setSearch(event.currentTarget.value)}
          w={420}
        />
        <Select
          aria-label="Role"
          placeholder="Any role"
          clearable
          data={ROLES.map((value) => ({ value, label: ROLE_LABELS[value] }))}
          value={role}
          onChange={(value) => {
            setRole(value as Role | null);
            paging.firstPage();
          }}
          w={180}
        />
      </Group>
      <PagedTable
        columns={columns}
        paging={paging}
        query={users}
        rowKey={(user) => user.id}
        empty="No users match."
      />
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
