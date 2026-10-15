import { Alert, Button, Group, Stack, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { useConfirmEmail, useResendEmailCode } from "../api/auth";

/** Enter the 6-digit code sent to an address (requirements §4.3). */
export function EmailCodeForm({ email }: { email: string }) {
  const [code, setCode] = useState("");
  const confirm = useConfirmEmail();
  const resend = useResendEmailCode();
  const valid = /^\d{6}$/.test(code);

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (valid) confirm.mutate(code);
      }}
    >
      <Stack gap="sm" maw={420}>
        <Text size="sm">
          We sent a 6-digit code to <b>{email}</b>. It is valid for 60 minutes. Check your spam
          folder if it does not arrive.
        </Text>
        <TextInput
          label="Confirmation code"
          value={code}
          onChange={(e) => setCode(e.currentTarget.value.replace(/\D/g, "").slice(0, 6))}
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="123456"
          w={160}
          data-autofocus
        />
        {confirm.isError && <Alert color="red">{confirm.error.message}</Alert>}
        <Group>
          <Button type="submit" disabled={!valid} loading={confirm.isPending}>
            Confirm
          </Button>
          <Button
            variant="subtle"
            loading={resend.isPending}
            onClick={() =>
              resend.mutate(undefined, {
                onSuccess: () =>
                  notifications.show({ color: "green", message: `New code sent to ${email}` }),
                onError: (e) => notifications.show({ color: "red", message: e.message }),
              })
            }
          >
            Send a new code
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
