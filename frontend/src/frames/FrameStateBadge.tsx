import { Badge, type BadgeProps } from "@mantine/core";

import type { FrameState } from "../api/client";
import { FRAME_STATE_LABELS, frameStateColor } from "../materials/labels";

/** A frame's status as a badge; states needing attention (on hold) are red. */
export function FrameStateBadge({ state, ...props }: { state: FrameState } & BadgeProps) {
  return (
    <Badge variant="light" color={frameStateColor(state)} {...props}>
      {FRAME_STATE_LABELS[state]}
    </Badge>
  );
}
