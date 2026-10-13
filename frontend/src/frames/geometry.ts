/**
 * Drawing geometry of the frame and plates, in pixels of the v1 images (frame: 455 × 631).
 * Positions are relative to their plate's image.
 */
import circle6Gas from "../assets/plates/6-circle-gas.png";
import circle8 from "../assets/plates/8-circle.png";
import slot8 from "../assets/plates/8-slot.png";
import emptyPlate from "../assets/plates/empty.png";
import frameImage from "../assets/plates/frame.png";

export type Side = "left" | "right";

export interface Spot {
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  shape: "circle" | "slot";
}

export interface PlateDrawing {
  image: string;
  width: number;
  height: number;
  spots: Spot[];
}

export const FRAME = { image: frameImage, width: 455, height: 631 };

/** Where a plate image sits on the frame, per side (a whole-frame plate uses its own offset). */
export const PLATE_OFFSET: Record<Side, { x: number; y: number }> = {
  left: { x: 62, y: 284 },
  right: { x: 234, y: 284 },
};
const WHOLE_FRAME_OFFSET = { x: 41, y: 285 };

/** Band of the frame that carries the barcode label. */
export const BARCODE_BAND = { y: 127, height: 125 };

const circle = (label: string, x: number, y: number, size: number): Spot => ({
  label,
  x,
  y,
  width: size,
  height: size,
  shape: "circle",
});

export const EMPTY_PLATE: PlateDrawing = { image: emptyPlate, width: 160, height: 316, spots: [] };

export const PLATE_DRAWINGS: Record<string, PlateDrawing> = {
  "8-circle": {
    image: circle8,
    width: 160,
    height: 316,
    spots: [
      circle("A", 12, 41, 48),
      circle("B", 100, 41, 48),
      circle("C", 56, 80, 48),
      circle("D", 14, 119, 48),
      circle("E", 100, 119, 48),
      circle("F", 56, 158, 48),
      circle("G", 14, 197, 48),
      circle("H", 100, 197, 48),
    ],
  },
  "8-slot": {
    image: slot8,
    width: 160,
    height: 316,
    spots: ["A", "B", "C", "D", "E", "F", "G", "H"].map((label, i) => ({
      label,
      x: 22,
      y: [40, 72, 103, 134, 165, 196, 227, 258][i]!,
      width: 116,
      height: 20,
      shape: "slot" as const,
    })),
  },
  "6-circle-gas": {
    image: circle6Gas,
    width: 372,
    height: 314,
    spots: [
      circle("A", 161, 193, 50),
      circle("B", 217, 153, 50),
      circle("C", 207, 94, 50),
      circle("D", 161, 133, 50),
      circle("E", 115, 94, 50),
      circle("F", 105, 153, 50),
    ],
  },
};

export function plateOffset(side: Side, blocksOtherSide: boolean) {
  return blocksOtherSide ? WHOLE_FRAME_OFFSET : PLATE_OFFSET[side];
}

/** "Left-A" for (left, A); matches the backend's position ids. */
export function positionId(side: Side, label: string): string {
  return `${side === "left" ? "Left" : "Right"}-${label}`;
}
