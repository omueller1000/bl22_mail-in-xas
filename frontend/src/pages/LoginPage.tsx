import {
  Alert,
  Anchor,
  Button,
  Card,
  Divider,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { Navigate, useNavigate, useSearchParams } from "react-router";

import { orcidLoginUrl, useDevLogin, useMe } from "../api/auth";
import type { Role } from "../api/client";
import { PageLoader } from "../auth/guards";
import { ROLE_LABELS, ROLES } from "../auth/roles";

const ERRORS: Record<string, string> = {
  orcid_cancelled: "The ORCID login was cancelled.",
  login_expired: "The login took too long or was started in another browser. Please try again.",
  orcid_failed: "ORCID could not confirm your login. Please try again.",
};

export function LoginPage() {
  const [params] = useSearchParams();
  const returnTo = safeReturnTo(params.get("return_to"));
  const error = params.get("error");
  const { data: me, isPending } = useMe();

  if (isPending) return <PageLoader />;
  if (me?.status === "authenticated") return <Navigate to={returnTo} replace />;
  if (me?.status === "registration_required" || me?.status === "email_confirmation_required") {
    return <Navigate to="/register" replace />;
  }

  return (
    <Stack maw={420} mx="auto" mt="xl">
      <Title order={2}>Sign in</Title>
      {error && (
        <Alert color="red">{ERRORS[error] ?? "Login failed. Please try again."}</Alert>
      )}

      {me?.orcid_login_enabled ? (
        <Button component="a" href={orcidLoginUrl(returnTo)} size="md" color="lime.8">
          Sign in with ORCID
        </Button>
      ) : (
        <Text c="dimmed">ORCID login is not configured on this server.</Text>
      )}
      <Text size="sm" c="dimmed">
        No ORCID iD yet?{" "}
        <Anchor href="https://orcid.org/register" target="_blank" rel="noreferrer">
          Register for free at orcid.org
        </Anchor>
        .
      </Text>

      {me?.dev_login_enabled && (
        <>
          <Divider label="Development only" />
          <DevLoginForm returnTo={returnTo} />
        </>
      )}
    </Stack>
  );
}

function DevLoginForm({ returnTo }: { returnTo: string }) {
  const navigate = useNavigate();
  const devLogin = useDevLogin();
  const form = useForm({
    initialValues: { orcid: "0000-0002-1825-0097", name: "Test User", role: "user" as Role },
    validate: {
      orcid: (value) =>
        /^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/.test(value.trim()) ? null : "Format 0000-0000-0000-0000",
    },
  });

  return (
    <Card withBorder>
      <form
        onSubmit={form.onSubmit((values) =>
          devLogin.mutate(
            { orcid: values.orcid.trim(), name: values.name.trim() || null, role: values.role },
            {
              onSuccess: (me) =>
                navigate(me.status === "authenticated" ? returnTo : "/register", { replace: true }),
            },
          ),
        )}
      >
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            Log in as any test ORCID iD without ORCID. The role is applied to the account.
          </Text>
          <TextInput label="ORCID iD" {...form.getInputProps("orcid")} />
          <TextInput
            label="Name"
            description="Leave empty to test an ORCID record with a private name"
            {...form.getInputProps("name")}
          />
          <Select
            label="Role"
            data={ROLES.map((role) => ({ value: role, label: ROLE_LABELS[role] }))}
            allowDeselect={false}
            {...form.getInputProps("role")}
          />
          {devLogin.isError && <Alert color="red">{devLogin.error.message}</Alert>}
          <Button type="submit" variant="light" loading={devLogin.isPending}>
            Dev login
          </Button>
        </Stack>
      </form>
    </Card>
  );
}

/** Only local paths (mirrors the backend's rule). */
function safeReturnTo(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return "/";
  }
  return value;
}
