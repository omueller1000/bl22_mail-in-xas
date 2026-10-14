import { ActionIcon, Tooltip } from "@mantine/core";
import { IconChartCovariate } from "@tabler/icons-react";
import { Link } from "react-router";


/**
 * Icon link to a frame's data; show it only where data exists. With `sampleId`, the viewer
 * opens on that sample's position.
 */
export function DataLink({ barcode, sampleId }: { barcode: string; sampleId?: string }) {
  return (
    <Tooltip label="View data" withArrow>
      <ActionIcon
        component={Link}
        to={`/frames/${barcode}/data${sampleId ? `?sample=${sampleId}` : ""}`}
        variant="subtle"
        size="sm"
        aria-label={`Data of ${barcode}`}
      >
        <IconChartCovariate size={16} />
      </ActionIcon>
    </Tooltip>
  );
}
