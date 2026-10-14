import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Checkbox,
  Grid,
  Group,
  Loader,
  SegmentedControl,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { IconDownload } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import type { DataView, SweepInfo } from "../api/client";
import {
  type CurveSpec,
  exportUrl,
  useFrameSweeps,
  useMergedCurve,
  useSweepCurves,
  useSweepDetail,
} from "../api/data";
import { useFrame } from "../api/frames";
import { useMeasurementOptions } from "../api/measurements";
import { PageLoader } from "../auth/guards";
import { Chart, type Trace } from "../data/Chart";
import { axisLabels, defaultSpectrum, SPECTRUM_LABELS, VIEW_LABELS } from "../data/labels";
import { describeMeasurement } from "../frames/measurementText";
import { FrameStateBadge } from "../frames/FrameStateBadge";

/** Plot a frame's measured data and download it (requirements §11.4, §11.5). */
export function DataPage() {
  const { barcode = "" } = useParams();
  // ?sample=<id> (from the Samples page) opens on that sample's position.
  const [search] = useSearchParams();
  const { data: frame, error: frameError } = useFrame(barcode);
  const { data: sweeps, isPending, error } = useFrameSweeps(barcode);

  if (frameError || error) return <Alert color="red">{(frameError ?? error)!.message}</Alert>;
  if (!frame || isPending) return <PageLoader />;

  return (
    <Stack>
      <Anchor component={Link} to={`/frames/${frame.barcode}`} size="sm">
        ← Frame {frame.barcode}
      </Anchor>
      <Group justify="space-between">
        <Group>
          <Title order={2}>
            Data · <span style={{ fontFamily: "var(--mantine-font-family-monospace)" }}>{frame.barcode}</span>
          </Title>
          <FrameStateBadge state={frame.state} />
        </Group>
        {sweeps.length > 0 && (
          <Button
            component="a"
            href={exportUrl(frame.barcode)}
            download
            variant="light"
            leftSection={<IconDownload size={16} />}
          >
            Download all (ZIP)
          </Button>
        )}
      </Group>
      {sweeps.length === 0 ? (
        <Text c="dimmed">
          No data yet. Measured sweeps appear here as soon as the beamline uploads them.
        </Text>
      ) : (
        <Viewer
          sweeps={sweeps}
          initialPosition={
            frame.positions.find((p) => p.sample_id === search.get("sample"))?.position
          }
          sampleNames={Object.fromEntries(frame.positions.map((p) => [p.position, p.sample_name]))}
        />
      )}
    </Stack>
  );
}

function Viewer({
  sweeps,
  sampleNames,
  initialPosition,
}: {
  sweeps: SweepInfo[];
  sampleNames: Record<string, string>;
  initialPosition?: string;
}) {
  const { data: options } = useMeasurementOptions();

  // Measurements that have data, grouped by position (sweeps come sorted by position).
  const measurements = useMemo(() => {
    const byId = new Map<string, SweepInfo[]>();
    for (const s of sweeps) byId.set(s.measurement_id, [...(byId.get(s.measurement_id) ?? []), s]);
    return byId;
  }, [sweeps]);

  // Sweeps are sorted by position and measurement number: this is the position's first one.
  const [measurementChoice, setMeasurementId] = useState<string | null>(
    () => sweeps.find((s) => s.position === initialPosition)?.measurement_id ?? null,
  );
  const measurementId =
    measurementChoice && measurements.has(measurementChoice)
      ? measurementChoice
      : sweeps[0]!.measurement_id;
  // Never empty: every listed measurement has sweeps.
  const ofMeasurement = measurements.get(measurementId)!;
  const batches = [...new Set(ofMeasurement.map((s) => s.batch_no))];
  const [batchChoice, setBatchChoice] = useState<number | null>(null);
  const batch = batchChoice !== null && batches.includes(batchChoice) ? batchChoice : batches.at(-1)!;
  const inBatch = useMemo(
    () => ofMeasurement.filter((s) => s.batch_no === batch),
    [ofMeasurement, batch],
  );
  const first = inBatch[0]!;

  const [view, setView] = useState<DataView>(first.spectra.length ? "spectrum" : "raw");
  const [spectrum, setSpectrum] = useState<string | null>(null);
  const [channel, setChannel] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  // Two merges: of all sweeps in the batch (whatever is checked) and of the checked ones.
  const [mergeAll, setMergeAll] = useState(false);
  const [mergeChecked, setMergeChecked] = useState(false);

  const processed = inBatch.some((s) => s.has_processed);
  const channels = first.channels.filter((c) => c !== "energy");
  const effectiveView: DataView =
    (view === "mu" || view === "chi") && !processed ? "spectrum" : view;
  const name =
    effectiveView === "spectrum"
      ? spectrum && first.spectra.includes(spectrum)
        ? spectrum
        : defaultSpectrum(first)
      : effectiveView === "raw"
        ? channel && channels.includes(channel)
          ? channel
          : channels[0]
        : undefined;
  const spec: CurveSpec | null =
    effectiveView === "spectrum" && !name ? null : { view: effectiveView, name };

  // μ(E) and χ(k) exist only for processed sweeps.
  const processedOnly = effectiveView === "mu" || effectiveView === "chi";
  const plottable = useMemo(
    () => (processedOnly ? inBatch.filter((s) => s.has_processed) : inBatch),
    [inBatch, processedOnly],
  );
  const shown = useMemo(() => plottable.filter((s) => !hidden.has(s.id)), [plottable, hidden]);
  const curves = useSweepCurves(shown, spec);
  const mergedAll = useMergedCurve(plottable, spec, mergeAll);
  const mergedChecked = useMergedCurve(shown, spec, mergeChecked);

  const traces = useMemo(() => {
    const result: Trace[] = shown.flatMap((s, i) => {
      const data = curves.data[i];
      return data ? [{ name: `Sweep ${s.sweep_no}`, x: data.x, y: data.y }] : [];
    });
    if (mergeAll && mergedAll.data && plottable.length > 1) {
      result.push({ name: `Merged, all (${plottable.length})`, ...mergedAll.data, emphasis: true });
    }
    if (mergeChecked && mergedChecked.data && shown.length > 1) {
      result.push({
        name: `Merged, checked (${shown.length})`,
        ...mergedChecked.data,
        emphasis: true,
        dashed: true,
      });
    }
    return result;
  }, [shown, plottable, curves.data, mergeAll, mergedAll.data, mergeChecked, mergedChecked.data]);
  const loading =
    curves.isLoading ||
    (mergeAll && mergedAll.isLoading) ||
    (mergeChecked && mergedChecked.isLoading);
  const failed = curves.error ?? mergedAll.error ?? mergedChecked.error;
  const [xLabel, yLabel] = axisLabels(effectiveView, name);

  const toggle = (id: string) =>
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const measurementOptions = useMemo(() => {
    const groups = new Map<string, { value: string; label: string }[]>();
    for (const [id, list] of measurements) {
      const s = list[0]!;
      const group = `${s.position} · ${sampleNames[s.position] ?? "sample"}`;
      const label = `#${s.number} · ${describeMeasurement(s.measured, options)}`;
      groups.set(group, [...(groups.get(group) ?? []), { value: id, label }]);
    }
    return [...groups].map(([group, items]) => ({ group, items }));
  }, [measurements, sampleNames, options]);

  return (
    <Stack>
      <Group align="end" wrap="wrap">
        <Select
          label="Measurement"
          data={measurementOptions}
          value={measurementId}
          onChange={(value) => value && setMeasurementId(value)}
          allowDeselect={false}
          w={{ base: "100%", sm: 460 }}
        />
        <Select
          label="Batch"
          data={batches.map((b) => ({ value: String(b), label: `Batch ${b}` }))}
          value={String(batch)}
          onChange={(value) => value && setBatchChoice(Number(value))}
          allowDeselect={false}
          w={120}
        />
      </Group>
      <Group align="end" wrap="wrap">
        <SegmentedControl
          value={effectiveView}
          onChange={(value) => setView(value as DataView)}
          data={(["spectrum", "raw", "mu", "chi"] as const).map((v) => ({
            value: v,
            label: VIEW_LABELS[v],
            disabled: (v === "mu" || v === "chi") && !processed,
          }))}
        />
        {effectiveView === "spectrum" && (
          <Select
            aria-label="Spectrum"
            data={first.spectra.map((s) => ({ value: s, label: SPECTRUM_LABELS[s] ?? s }))}
            value={name ?? null}
            onChange={setSpectrum}
            allowDeselect={false}
            w={300}
          />
        )}
        {effectiveView === "raw" && (
          <Select
            aria-label="Channel"
            data={channels}
            value={name ?? null}
            onChange={setChannel}
            allowDeselect={false}
            searchable
            w={200}
          />
        )}
        {!processed && (
          <Text size="xs" c="dimmed">
            μ(E) and χ(k) appear once the sweeps are processed.
          </Text>
        )}
      </Group>
      <Grid gap="md">
        <Grid.Col span={{ base: 12, md: 3 }}>
          <Card withBorder>
            <Stack gap="xs">
              <Group justify="space-between">
                <Text fw={600} size="sm">
                  Sweeps
                </Text>
                <Group gap={4}>
                  <Button size="compact-xs" variant="subtle" onClick={() => setHidden(new Set())}>
                    All
                  </Button>
                  <Button
                    size="compact-xs"
                    variant="subtle"
                    onClick={() => setHidden(new Set(plottable.map((s) => s.id)))}
                  >
                    None
                  </Button>
                </Group>
              </Group>
              {plottable.map((s) => (
                <Checkbox
                  key={s.id}
                  label={`Sweep ${s.sweep_no}`}
                  checked={!hidden.has(s.id)}
                  onChange={() => toggle(s.id)}
                />
              ))}
              <Switch
                mt="xs"
                label="Merge all sweeps"
                checked={mergeAll}
                onChange={(e) => setMergeAll(e.currentTarget.checked)}
                disabled={plottable.length < 2}
              />
              <Switch
                label="Merge checked sweeps"
                checked={mergeChecked}
                onChange={(e) => setMergeChecked(e.currentTarget.checked)}
                disabled={shown.length < 2}
              />
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 9 }}>
          <Card withBorder pos="relative">
            {failed && <Alert color="red">{failed.message}</Alert>}
            {loading && (
              <Group gap="xs" pos="absolute" top={8} right={12} style={{ zIndex: 1 }}>
                <Loader size="xs" />
                <Text size="xs" c="dimmed">
                  Loading…
                </Text>
              </Group>
            )}
            {/* "Merge all sweeps" does not depend on which sweeps are checked. */}
            {shown.length === 0 && !(mergeAll && plottable.length > 1) ? (
              <Text c="dimmed" ta="center" py="xl">
                Select at least one sweep, or merge all sweeps.
              </Text>
            ) : (
              <Chart traces={traces} xLabel={xLabel} yLabel={yLabel} />
            )}
          </Card>
        </Grid.Col>
      </Grid>
      <MetadataCard sweeps={inBatch} />
    </Stack>
  );
}

function MetadataCard({ sweeps }: { sweeps: SweepInfo[] }) {
  const [choice, setChoice] = useState<string | null>(null);
  const sweepId = choice && sweeps.some((s) => s.id === choice) ? choice : sweeps[0]!.id;
  const { data: detail } = useSweepDetail(sweepId);

  return (
    <Card withBorder>
      <Stack gap="sm">
        <Group justify="space-between">
          <Text fw={600}>Metadata</Text>
          <Select
            aria-label="Metadata of sweep"
            data={sweeps.map((s) => ({ value: s.id, label: `Sweep ${s.sweep_no}` }))}
            value={sweepId}
            onChange={setChoice}
            allowDeselect={false}
            w={140}
          />
        </Group>
        {!detail ? (
          <Loader size="sm" />
        ) : (
          <Grid gap="lg">
            <Grid.Col span={{ base: 12, md: 6 }}>
              <Text size="sm" fw={500} mb={4}>
                Measured{" "}
                <Badge size="xs" variant="light" color="gray">
                  {detail.sweep.points} points
                </Badge>
              </Text>
              <KeyValues
                values={{
                  ...detail.sweep.measured,
                  uploaded: new Date(detail.sweep.uploaded_at).toLocaleString(),
                  ...detail.metadata,
                }}
              />
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 6 }}>
              <Text size="sm" fw={500} mb={4}>
                Processing
              </Text>
              {detail.processed ? (
                <KeyValues
                  values={{
                    ...detail.processed.metadata,
                    uploaded: new Date(detail.processed.uploaded_at).toLocaleString(),
                  }}
                />
              ) : (
                <Text size="sm" c="dimmed">
                  Not processed yet.
                </Text>
              )}
            </Grid.Col>
          </Grid>
        )}
      </Stack>
    </Card>
  );
}

function KeyValues({ values }: { values: Record<string, unknown> }) {
  return (
    <Table striped withRowBorders={false} fz="sm" verticalSpacing={2}>
      <Table.Tbody>
        {Object.entries(values).map(([key, value]) => (
          <Table.Tr key={key}>
            <Table.Td c="dimmed" w="45%">
              {key}
            </Table.Td>
            <Table.Td style={{ wordBreak: "break-word" }}>
              {typeof value === "object" ? JSON.stringify(value) : String(value)}
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
