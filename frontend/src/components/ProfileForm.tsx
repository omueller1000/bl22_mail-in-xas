import { Alert, Button, Fieldset, Group, SimpleGrid, Stack, TextInput } from "@mantine/core";
import { isEmail, isNotEmpty, useForm } from "@mantine/form";

import type { Profile } from "../api/client";

export interface ProfileFormValues {
  name: string;
  email: string;
  phone: string;
  affiliation: string;
  care_of: string;
  street1: string;
  street2: string;
  city: string;
  region: string;
  postal_code: string;
  country: string;
}

interface Props {
  initial?: Profile;
  /** Show a required name field (registration when ORCID provided no name). */
  askName?: boolean;
  submitLabel: string;
  submitting: boolean;
  error?: string | null;
  onSubmit: (profile: Profile, name: string | null) => void;
}

/** Contact details and shipping address (requirements §4.1). */
export function ProfileForm({ initial, askName, submitLabel, submitting, error, onSubmit }: Props) {
  const address = initial?.shipping_address;
  const form = useForm<ProfileFormValues>({
    mode: "uncontrolled",
    initialValues: {
      name: "",
      email: initial?.email ?? "",
      phone: initial?.phone ?? "",
      affiliation: initial?.affiliation ?? "",
      care_of: address?.care_of ?? "",
      street1: address?.street1 ?? "",
      street2: address?.street2 ?? "",
      city: address?.city ?? "",
      region: address?.region ?? "",
      postal_code: address?.postal_code ?? "",
      country: address?.country ?? "",
    },
    validate: {
      name: (value) => (askName && !value.trim() ? "Name is required" : null),
      email: isEmail("Enter a valid email address"),
      phone: (value) => (value.trim().length < 5 ? "Enter a phone number" : null),
      affiliation: isNotEmpty("Affiliation is required"),
      street1: isNotEmpty("Street is required"),
      city: isNotEmpty("City is required"),
      country: (value) => (value.trim().length < 2 ? "Country is required" : null),
    },
  });

  const handleSubmit = form.onSubmit((v) => {
    const optional = (value: string) => value.trim() || null;
    onSubmit(
      {
        email: v.email.trim(),
        phone: v.phone.trim(),
        affiliation: v.affiliation.trim(),
        shipping_address: {
          care_of: optional(v.care_of),
          street1: v.street1.trim(),
          street2: optional(v.street2),
          city: v.city.trim(),
          region: optional(v.region),
          postal_code: optional(v.postal_code),
          country: v.country.trim(),
        },
      },
      askName ? v.name.trim() : null,
    );
  });

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Stack maw={640}>
        <Fieldset legend="Contact">
          <Stack gap="sm">
            {askName && (
              <TextInput
                label="Name"
                description="Your ORCID record does not share your name. It cannot be changed later."
                withAsterisk
                key={form.key("name")}
                {...form.getInputProps("name")}
              />
            )}
            <TextInput label="Email" type="email" withAsterisk key={form.key("email")} {...form.getInputProps("email")} />
            <TextInput label="Phone" description="Needed for shipping" withAsterisk key={form.key("phone")} {...form.getInputProps("phone")} />
            <TextInput label="Affiliation" withAsterisk key={form.key("affiliation")} {...form.getInputProps("affiliation")} />
          </Stack>
        </Fieldset>

        <Fieldset legend="Shipping address">
          <Stack gap="sm">
            <TextInput label="c/o" key={form.key("care_of")} {...form.getInputProps("care_of")} />
            <TextInput label="Street" withAsterisk key={form.key("street1")} {...form.getInputProps("street1")} />
            <TextInput label="Street (line 2)" key={form.key("street2")} {...form.getInputProps("street2")} />
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <TextInput label="City" withAsterisk key={form.key("city")} {...form.getInputProps("city")} />
              <TextInput label="State / province" key={form.key("region")} {...form.getInputProps("region")} />
              <TextInput label="Postal code" key={form.key("postal_code")} {...form.getInputProps("postal_code")} />
              <TextInput label="Country" withAsterisk key={form.key("country")} {...form.getInputProps("country")} />
            </SimpleGrid>
          </Stack>
        </Fieldset>

        {error && (
          <Alert color="red" title="Could not save">
            {error}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button type="submit" loading={submitting}>
            {submitLabel}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
