import { AppShell, Badge, Burger, Button, Group, Menu, NavLink, Text, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  type Icon,
  IconAdjustments,
  IconApi,
  IconBolt,
  IconBuildingWarehouse,
  IconClipboardList,
  IconDirectionSign,
  IconFlask,
  IconHeartbeat,
  IconHome,
  IconMail,
  IconPackage,
  IconScan,
  IconStack,
  IconStack2,
  IconTruckDelivery,
  IconUser,
  IconUsers,
} from "@tabler/icons-react";
import { Fragment } from "react";
import { Link, NavLink as RouterNavLink, Outlet, useNavigate } from "react-router";

import { useLogout, useMe } from "../api/auth";
import type { Role } from "../api/client";
import { hasRole, ROLE_LABELS } from "../auth/roles";

interface NavItem {
  to: string;
  label: string;
  /** Shown left of the label. */
  icon: Icon;
  /** Minimum role; omitted = visible to everyone. */
  role?: Role;
  /** Heading shown above the first item of a section. */
  section?: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Home", icon: IconHome },
  { to: "/samples", label: "My Samples", icon: IconFlask, role: "user" },
  { to: "/frames", label: "My Frames", icon: IconStack, role: "user" },
  { to: "/materials", label: "Request Materials", icon: IconPackage, role: "user" },
  { to: "/account", label: "My Account", icon: IconUser, role: "user" },
  { to: "/users", label: "All Users", icon: IconUsers, role: "operator", section: "Operator" },
  { to: "/operator/frames", label: "All Frames", icon: IconStack2, role: "operator", section: "Operator" },
  { to: "/operator/scan", label: "Frame Actions", icon: IconDirectionSign, role: "operator", section: "Operator" },
  {
    to: "/operator/storage",
    label: "Internal Storage",
    icon: IconBuildingWarehouse,
    role: "operator",
    section: "Operator",
  },
  {
    to: "/operator/requests",
    label: "Material Requests",
    icon: IconClipboardList,
    role: "operator",
    section: "Operator",
  },
  {
    to: "/operator/shipping",
    label: "Shipping",
    icon: IconTruckDelivery,
    role: "operator",
    section: "Operator",
  },
  {
    to: "/operator/barcodes",
    label: "Generate Barcodes",
    icon: IconScan,
    role: "operator",
    section: "Operator",
  },
  { to: "/admin/service-clients", label: "API", icon: IconApi, role: "admin", section: "Admin" },
  {
    to: "/admin/xas-parameters",
    label: "XAS Parameters",
    icon: IconAdjustments,
    role: "admin",
    section: "Admin",
  },
  { to: "/admin/beamline", label: "Beamline", icon: IconBolt, role: "admin", section: "Admin" },
  { to: "/admin/email", label: "Email", icon: IconMail, role: "admin", section: "Admin" },
  { to: "/admin/status", label: "Status", icon: IconHeartbeat, role: "admin", section: "Admin" },
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
        {items.map((item, index) => (
          <Fragment key={item.to}>
            {item.section && item.section !== items[index - 1]?.section && (
              <Text size="xs" fw={700} c="dimmed" tt="uppercase" mt="md" mb={4} px="sm">
                {item.section}
              </Text>
            )}
            <NavLink
              component={RouterNavLink}
              to={item.to}
              end={item.to === "/"}
              label={item.label}
              leftSection={<item.icon size={18} stroke={1.5} />}
              onClick={close}
            />
          </Fragment>
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
        {me.status === "authenticated" && (
          <Menu.Item component={Link} to="/account">
            Account
          </Menu.Item>
        )}
        <Menu.Item
          color="red"
          onClick={() =>
            logout.mutate(undefined, { onSuccess: () => navigate("/login", { replace: true }) })
          }
        >
          Sign out
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
