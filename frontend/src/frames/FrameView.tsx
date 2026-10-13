import { Box, Text, Tooltip, UnstyledButton } from "@mantine/core";
import type { CSSProperties } from "react";

import type { Frame, PlateType } from "../api/client";
import {
  BARCODE_BAND,
  EMPTY_PLATE,
  FRAME,
  PLATE_DRAWINGS,
  plateOffset,
  positionId,
  type Side,
  type Spot,
} from "./geometry";

interface Props {
  frame: Pick<Frame, "barcode" | "plates" | "positions">;
  plateTypes: PlateType[];
  /** Called with a position id ("Left-A"); omit for a read-only drawing. */
  onPositionClick?: (position: string) => void;
  selected?: string | null;
  maxWidth?: number;
}

const SAMPLE_COLOR = "rgba(30, 144, 255, 1)";
// The colour extends a little under the plate, so no gap shows at the edge of a hole.
const FILL_MARGIN = 2;

/**
 * The frame with its plates and clickable sample positions (drawings from v1).
 *
 * Layers, bottom to top: sample colours, frame image, plate images, click areas. The frame's
 * window and the plates' holes are transparent, so a sample's colour shows through its hole.
 */
export function FrameView({ frame, plateTypes, onPositionClick, selected, maxWidth = 455 }: Props) {
  const type = (id: string | null | undefined) => plateTypes.find((t) => t.id === id);
  const samples = new Map(frame.positions.map((p) => [p.position, p.sample_name]));
  const left = type(frame.plates.left);
  const right = type(frame.plates.right);

  // A plate spanning the whole frame (6-Circle-Gas) is drawn once; otherwise one per side.
  const mounted: { side: Side; plate: PlateType | undefined }[] = left?.blocks_other_side
    ? [{ side: "left", plate: left }]
    : right?.blocks_other_side
      ? [{ side: "right", plate: right }]
      : [
          { side: "left", plate: left },
          { side: "right", plate: right },
        ];

  // Everything in frame pixel coordinates.
  const plates = mounted.map(({ side, plate }) => {
    const drawing = (plate && PLATE_DRAWINGS[plate.id]) || EMPTY_PLATE;
    const offset = plateOffset(side, plate?.blocks_other_side ?? false);
    return { side, plate, drawing, offset };
  });
  const spots = plates.flatMap(({ side, drawing, offset }) =>
    drawing.spots.map((spot) => ({
      ...spot,
      id: positionId(side, spot.label),
      x: offset.x + spot.x,
      y: offset.y + spot.y,
    })),
  );

  return (
    <Box
      pos="relative"
      w="100%"
      maw={maxWidth}
      style={{ aspectRatio: `${FRAME.width} / ${FRAME.height}` }}
    >
      {spots
        .filter((spot) => samples.has(spot.id))
        .map((spot) => (
          <div
            key={spot.id}
            data-testid={`sample-${spot.id}`}
            style={{ ...rect(grow(spot, FILL_MARGIN)), ...shape(spot), background: SAMPLE_COLOR }}
          />
        ))}

      <img src={FRAME.image} alt="" style={layer} />
      {plates.map(({ side, plate, drawing, offset }) => (
        <img
          key={side}
          src={drawing.image}
          alt={plate ? plate.name : `empty ${side} side`}
          style={{
            ...rect({ ...offset, width: drawing.width, height: drawing.height }),
            pointerEvents: "none",
          }}
        />
      ))}

      <Text
        ff="monospace"
        fw={700}
        fz="xl"
        ta="center"
        pos="absolute"
        left={0}
        right={0}
        top={pct(BARCODE_BAND.y + BARCODE_BAND.height / 2 - 14, FRAME.height)}
        style={{ letterSpacing: 2 }}
      >
        {frame.barcode}
      </Text>

      {spots.map((spot) => {
        const sample = samples.get(spot.id);
        const label = `${spot.id}: ${sample ?? "empty"}`;
        return (
          <Tooltip key={spot.id} label={label} withArrow>
            <UnstyledButton
              aria-label={label}
              disabled={!onPositionClick}
              onClick={() => onPositionClick?.(spot.id)}
              style={{
                ...rect(spot),
                ...shape(spot),
                outline: selected === spot.id ? "3px solid orange" : undefined,
                cursor: onPositionClick ? "pointer" : "default",
              }}
            />
          </Tooltip>
        );
      })}
    </Box>
  );
}

// Percentages of the frame image, so the drawing scales with its container.
const pct = (value: number, total: number) => `${(value / total) * 100}%`;

function rect(area: { x: number; y: number; width: number; height: number }): CSSProperties {
  return {
    position: "absolute",
    left: pct(area.x, FRAME.width),
    top: pct(area.y, FRAME.height),
    width: pct(area.width, FRAME.width),
    height: pct(area.height, FRAME.height),
  };
}

function grow<T extends { x: number; y: number; width: number; height: number }>(area: T, by: number): T {
  return { ...area, x: area.x - by, y: area.y - by, width: area.width + 2 * by, height: area.height + 2 * by };
}

function shape(spot: Pick<Spot, "shape">): CSSProperties {
  return { borderRadius: spot.shape === "circle" ? "50%" : 10 };
}

const layer: CSSProperties = {
  position: "absolute",
  inset: 0,
  width: "100%",
  height: "100%",
  pointerEvents: "none",
};
