import { Anchor, Button, Group, Stack, Text, TextInput, Title } from "@mantine/core";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router";

import { useMe, useRegister, useUpdateProfile } from "../api/auth";
import type { User } from "../api/client";
import { PageLoader } from "../auth/guards";
import { EmailCodeForm } from "../components/EmailCodeForm";
import { ProfileForm } from "../components/ProfileForm";

/** Create the account after the first login (requirements §4). */
export function RegisterPage() {
  const { data: me, isPending } = useMe();
  const register = useRegister();
  const navigate = useNavigate();

  if (isPending) return <PageLoader />;
  if (!me || me.status === "anonymous") return <Navigate to="/login" replace />;
  if (me.status === "authenticated") return <Navigate to="/" replace />;
  if (me.status === "email_confirmation_required" && me.user) {
    return (
      <Stack>
        <Title order={2}>Confirm your email address</Title>
        <Text>Your account is created. Confirm your email address to start using the portal.</Text>
        <EmailCodeForm email={me.user.email} />
        <ChangeAddress profile={me.user} />
      </Stack>
    );
  }

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

/** A typo in the address: send the code to another one. */
function ChangeAddress({ profile }: { profile: User }) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState(profile.email);
  const update = useUpdateProfile();
  if (!open) {
    return (
      <Text size="sm" c="dimmed">
        Wrong address?{" "}
        <Anchor component="button" size="sm" onClick={() => setOpen(true)}>
          Use another one
        </Anchor>
      </Text>
    );
  }
  return (
    <Group align="end">
      <TextInput
        label="Email address"
        value={email}
        onChange={(e) => setEmail(e.currentTarget.value)}
        error={update.error?.message}
        w={300}
      />
      <Button
        variant="light"
        loading={update.isPending}
        onClick={() =>
          update.mutate(
            {
              email: email.trim(),
              phone: profile.phone,
              affiliation: profile.affiliation,
              shipping_address: profile.shipping_address,
            },
            { onSuccess: () => setOpen(false) },
          )
        }
      >
        Send code
      </Button>
    </Group>
  );
}
