import { TextInput } from "@mantine/core";
import { useRef, useState } from "react";

export const BARCODE_PATTERN = /^[A-Z]{4}-[A-Z]{4}$/;

interface Props {
  onScan: (barcode: string) => void;
  label?: string;
  disabled?: boolean;
}

/**
 * Input for handheld barcode scanners, which type the code followed by Enter.
 * Also works for typing a code by hand. Keeps focus so the next scan lands here.
 */
export function ScanInput({ onScan, label = "Scan barcode", disabled }: Props) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLInputElement>(null);

  return (
    <TextInput
      ref={ref}
      label={label}
      placeholder="ABCD-EFGH"
      value={value}
      error={error}
      disabled={disabled}
      autoFocus
      autoComplete="off"
      onChange={(event) => {
        setValue(event.currentTarget.value);
        setError(null);
      }}
      onKeyDown={(event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        const code = value.trim().toUpperCase();
        if (!code) return;
        if (!BARCODE_PATTERN.test(code)) {
          setError(`"${code}" is not a barcode (format ABCD-EFGH)`);
          return;
        }
        onScan(code);
        setValue("");
        ref.current?.focus();
      }}
      maw={320}
    />
  );
}
