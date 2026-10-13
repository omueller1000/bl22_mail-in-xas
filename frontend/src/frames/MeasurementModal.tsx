import {
  Alert,
  Button,
  Group,
  Modal,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Tooltip,
} from "@mantine/core";
import { type ReactNode, useState } from "react";

import type { Frame, Measurement, MeasurementInput } from "../api/client";
import {
  useAddMeasurement,
  useMeasurementOptions,
  useUpdateMeasurement,
} from "../api/measurements";

type Settings = Omit<MeasurementInput, "version">;

const DEFAULTS: Settings = {
  technique: "exafs",
  element: "Fe",
  edge: "K",
  detection: "transmission",
  beam: "unfocused",
};

const BEAM_HINTS: Record<string, string> = {
  unfocused: "DEFAULT: The beam is slitted to illuminate the entire sample",
  focused: "Using a polycapillary the beam is focused to about 0.4 mm x 0.4 mm",
};

const TECHNIQUE_HINTS: Record<string, ReactNode> = {
  xanes: (
    <>
      XANES: −200 eV to +300 eV (8.8 Å<sup>−1</sup>)
    </>
  ),
  exafs: (
    <>
      EXAFS: −200 eV to 16 Å<sup>−1</sup>
    </>
  ),
};

// New measurements start with the element and edge of the last one saved (in this browser).
const LAST_KEY = "ht-xas.lastElementEdge";

function lastElementEdge(): Pick<Settings, "element" | "edge"> | null {
  try {
    const stored = JSON.parse(localStorage.getItem(LAST_KEY) ?? "null");
    return stored?.element && stored?.edge ? { element: stored.element, edge: stored.edge } : null;
  } catch {
    return null; // storage unavailable or corrupt: fall back to the defaults
  }
}

function rememberElementEdge({ element, edge }: Settings) {
  try {
    localStorage.setItem(LAST_KEY, JSON.stringify({ element, edge }));
  } catch {
    // storage unavailable (private window, blocked); not essential
  }
}

interface Props {
  frame: Frame;
  position: string;
  sampleName: string;
  /** The measurement to edit; omit to add a new one. */
  measurement?: Measurement;
  onClose: () => void;
}

/** Add or edit one measurement of a position (requirements §5.3). */
export function MeasurementModal({ frame, position, sampleName, measurement, onClose }: Props) {
  const { data: options } = useMeasurementOptions();
  const add = useAddMeasurement(frame);
  const update = useUpdateMeasurement(frame);
  const mutation = measurement ? update : add;
  const [settings, setSettings] = useState<Settings>(
    measurement
      ? {
          technique: measurement.technique,
          element: measurement.element,
          edge: measurement.edge,
          detection: measurement.detection,
          beam: measurement.beam,
        }
      : { ...DEFAULTS, ...lastElementEdge() },
  );
  const set = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setSettings((s) => ({ ...s, [key]: value }));

  const save = () => {
    const done = {
      onSuccess: () => {
        rememberElementEdge(settings);
        onClose();
      },
    };
    if (measurement) update.mutate({ id: measurement.id, ...settings }, done);
    else add.mutate({ position, ...settings }, done);
  };

  return (
    <Modal
      opened
      onClose={onClose}
      title={
        measurement
          ? `Measurement ${measurement.number} at ${position}`
          : `New measurement at ${position}`
      }
    >
      {options && (
        <Stack>
          <Text size="sm" c="dimmed">
            Sample: {sampleName}
          </Text>
          <Stack gap={4}>
            <Text size="sm" fw={500}>
              Technique
            </Text>

            <SegmentedControl
              data={options.techniques.map((t) => ({
                value: t.value,
                label: (
                  <Tooltip label={TECHNIQUE_HINTS[t.value]} withArrow multiline maw={280}>
                    <span style={{ display: "block" }}>{t.label}</span>
                  </Tooltip>
                ),
              }))}
              value={settings.technique}
              onChange={(v) => set("technique", v as Settings["technique"])}
            />
          </Stack>
          <Group grow align="flex-start">
            <Select
              label="Element"
              searchable
              allowDeselect={false}
              data={options.elements.map((e) => ({ value: e.symbol, label: `${e.symbol} (${e.z})` }))}
              value={settings.element}
              onChange={(v) => v && set("element", v)}
              nothingFoundMessage="Only Ti to Bi"
            />
            <Stack gap={4}>
              <Text size="sm" fw={500}>
                Edge
              </Text>
              <SegmentedControl
                data={options.edges}
                value={settings.edge}
                onChange={(v) => set("edge", v as Settings["edge"])}
              />
            </Stack>
          </Group>
          <Select
            label="Detection"
            allowDeselect={false}
            data={options.detections}
            value={settings.detection}
            onChange={(v) => v && set("detection", v as Settings["detection"])}
          />
          <Stack gap={4}>
            <Text size="sm" fw={500}>
              Beam
            </Text>
            <SegmentedControl
              data={options.beams.map((b) => ({
                value: b.value,
                label: (
                  <Tooltip label={BEAM_HINTS[b.value]} withArrow multiline maw={280}>
                    <span style={{ display: "block" }}>{b.label}</span>
                  </Tooltip>
                ),
              }))}
              value={settings.beam ?? "unfocused"}
              onChange={(v) => set("beam", v as Settings["beam"])}
            />
          </Stack>
          {measurement?.executed && (
            <Alert color="yellow">
              This measurement has already been run. Changing it affects only future runs; data
              already collected keeps its own settings.
            </Alert>
          )}
          {mutation.isError && <Alert color="red">{mutation.error.message}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={save} loading={mutation.isPending}>
              {measurement ? "Save" : "Add measurement"}
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
