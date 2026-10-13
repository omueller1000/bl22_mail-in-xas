import { Stack, Text, Title } from "@mantine/core";
import { Navigate, useNavigate } from "react-router";

import { useMe, useRegister } from "../api/auth";
import { PageLoader } from "../auth/guards";
import { ProfileForm } from "../components/ProfileForm";

/** Create the account after the first login (requirements §4). */
export function RegisterPage() {
  const { data: me, isPending } = useMe();
  const register = useRegister();
  const navigate = useNavigate();

  if (isPending) return <PageLoader />;
  if (!me || me.status === "anonymous") return <Navigate to="/login" replace />;
  if (me.status === "authenticated") return <Navigate to="/" replace />;

  return (
    <Stack>
      <Title order={2}>Create your account</Title>
      <Text>
        Signed in with ORCID iD <b>{me.orcid}</b>
        {me.orcid_name && (
          <>
            {" "}
            as <b>{me.orcid_name}</b>
          </>
        )}
        . We need your contact details and shipping address to send you sample frames.
      </Text>
      <ProfileForm
        askName={!me.orcid_name}
        submitLabel="Create account"
        submitting={register.isPending}
        error={register.error?.message}
        onSubmit={(profile, name) =>
          register.mutate({ ...profile, name }, { onSuccess: () => navigate("/", { replace: true }) })
        }
      />
    </Stack>
  );
}
