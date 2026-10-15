import { Center, Loader, Stack, Text, Title } from "@mantine/core";
import { Navigate, Outlet, useLocation } from "react-router";

import { useMe } from "../api/auth";
import type { Role } from "../api/client";
import { hasRole } from "./roles";

/** Pages below this route need a registered, logged-in user. */
export function RequireUser() {
  const { data: me, isPending, isError } = useMe();
  const location = useLocation();

  if (isPending) return <PageLoader />;
  if (isError) return <Text c="red">Could not reach the server.</Text>;
  if (me.status === "anonymous") {
    const returnTo = location.pathname + location.search;
    return <Navigate to={`/login?return_to=${encodeURIComponent(returnTo)}`} replace />;
  }
  // Registration (including the email confirmation) is completed on the register page.
  if (me.status === "registration_required" || me.status === "email_confirmation_required") {
    return <Navigate to="/register" replace />;
  }
  return <Outlet />;
}

/** Pages below this route need at least the given role (use inside RequireUser). */
export function RequireRole({ role }: { role: Role }) {
  const { data: me } = useMe();
  if (!me?.user || !hasRole(me.user.role, role)) {
    return (
      <Stack>
        <Title order={2}>Not allowed</Title>
        <Text>This page requires the {role} role.</Text>
      </Stack>
    );
  }
  return <Outlet />;
}

export function PageLoader() {
  return (
    <Center py="xl">
      <Loader />
    </Center>
  );
}
