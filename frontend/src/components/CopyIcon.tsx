import { ActionIcon, CopyButton, Tooltip } from "@mantine/core";
import { IconCheck, IconCopy } from "@tabler/icons-react";

/** Small icon button that copies `value` to the clipboard. */
export function CopyIcon({ value, label }: { value: string; label: string }) {
  return (
    <CopyButton value={value} timeout={1500}>
      {({ copied, copy }) => (
        <Tooltip label={copied ? "Copied" : `Copy ${label}`} withArrow position="right">
          <ActionIcon
            variant="subtle"
            color={copied ? "green" : "gray"}
            size="sm"
            onClick={copy}
            aria-label={`Copy ${label}`}
          >
            {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
          </ActionIcon>
        </Tooltip>
      )}
    </CopyButton>
  );
}
