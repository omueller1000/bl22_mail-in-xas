import { Alert, Badge, Button, Group, Stack, Table, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";

import { useCancelEmailChange, useMe, useUpdateProfile } from "../api/auth";
import { ROLE_LABELS } from "../auth/roles";
import { EmailCodeForm } from "../components/EmailCodeForm";
import { ProfileForm } from "../components/ProfileForm";

export function AccountPage() {
  const { data: me } = useMe();
  const update = useUpdateProfile();
  const user = me?.user;
  if (!user) return null; // RequireUser guarantees a user

  return (
    <Stack>
      <Title order={2}>My Account</Title>
      <Table variant="vertical" withTableBorder maw={640}>
        <Table.Tbody>
          <Table.Tr>
            <Table.Th w={160}>Name</Table.Th>
            <Table.Td>{user.name}</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Th>ORCID iD</Table.Th>
            <Table.Td>{user.orcid}</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Th>Role</Table.Th>
            <Table.Td>
              <Group>
                <Badge variant="light">{ROLE_LABELS[user.role]}</Badge>
              </Group>
            </Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
      {user.pending_email && <PendingEmail address={user.pending_email} />}
      <ProfileForm
        // Re-create the form after a save, so it shows exactly what the server stored.
        key={JSON.stringify(user)}
        initial={user}
        submitLabel="Save changes"
        submitting={update.isPending}
        error={update.error?.message}
        onSubmit={(profile) =>
          update.mutate(profile, {
            onSuccess: (saved) =>
              notifications.show({
                color: "green",
                message:
                  saved.pending_email && saved.pending_email !== user.pending_email
                    ? `Account saved. Confirm ${saved.pending_email} with the code we sent to it.`
                    : "Account saved",
              }),
          })
        }
      />
    </Stack>
  );
}

/** A requested new address: used once confirmed; until then the old one stays. */
function PendingEmail({ address }: { address: string }) {
  const cancel = useCancelEmailChange();
  return (
    <Alert color="yellow" title="Confirm your new email address" maw={640}>
      <Stack gap="sm">
        <EmailCodeForm email={address} />
        <Group>
          <Button
            variant="subtle"
            color="gray"
            size="xs"
            loading={cancel.isPending}
            onClick={() => cancel.mutate()}
          >
            Keep the current address
          </Button>
        </Group>
      </Stack>
    </Alert>
  );
}
