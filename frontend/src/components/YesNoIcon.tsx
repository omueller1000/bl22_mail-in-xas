import { IconCheck, IconX } from "@tabler/icons-react";

/** Green check for yes, red cross for no, "—" when unknown. */
export function YesNoIcon({ value }: { value: boolean | null }) {
  if (value === null) return <>—</>;
  return value ? (
    <IconCheck size={16} color="var(--mantine-color-green-6)" aria-label="yes" />
  ) : (
    <IconX size={16} color="var(--mantine-color-red-6)" aria-label="no" />
  );
}
