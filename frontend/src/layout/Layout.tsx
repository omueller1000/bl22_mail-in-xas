import { AppShell, Badge, Burger, Button, Group, Menu, NavLink, Text, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { Link, NavLink as RouterNavLink, Outlet, useNavigate } from "react-router";

import { useLogout, useMe } from "../api/auth";
import type { Role } from "../api/client";
import { hasRole, ROLE_LABELS } from "../auth/roles";

interface NavItem {
  to: string;
  label: string;
  /** Minimum role; omitted = visible to everyone. */
  role?: Role;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Home" },
  { to: "/account", label: "Account", role: "user" },
  { to: "/users", label: "Users", role: "operator" },
];

export function Layout() {
  const [opened, { toggle, close }] = useDisclosure();
  const { data: me } = useMe();
  const role = me?.user?.role;
  const items = NAV_ITEMS.filter((item) => !item.role || (role && hasRole(role, item.role)));

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Menu" />
            <Title order={3}>BL22 Mail-in XAS</Title>
          </Group>
          <UserMenu />
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        {items.map((item) => (
          <NavLink
            key={item.to}
            component={RouterNavLink}
            to={item.to}
            end={item.to === "/"}
            label={item.label}
            onClick={close}
          />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

function UserMenu() {
  const { data: me } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();

  if (!me || me.status === "anonymous") {
    return (
      <Button component={Link} to="/login" variant="light" size="xs">
        Sign in
      </Button>
    );
  }

  const label = me.user?.name ?? me.orcid_name ?? me.orcid;
  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <Button variant="subtle" size="xs">
          <Group gap={6} wrap="nowrap">
            <Text size="sm" truncate maw={160}>
              {label}
            </Text>
            {me.user && me.user.role !== "user" && (
              <Badge size="xs" variant="light">
                {ROLE_LABELS[me.user.role]}
              </Badge>
            )}
          </Group>
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>{me.orcid}</Menu.Label>
        {me.user && (
          <Menu.Item component={Link} to="/account">
            Account
          </Menu.Item>
        )}
        <Menu.Item
          color="red"
          onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/") })}
        >
          Sign out
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
