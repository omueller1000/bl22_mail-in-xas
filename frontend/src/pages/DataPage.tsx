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

import type { ProcessedSpectrum, SweepInfo } from "../api/client";
import {
  type CurveSpec,
  exportUrl,
  useFrameSweeps,
  useMergedCurve,
  useProcessed,
  useSweepCurves,
  useSweepDetail,
} from "../api/data";
import { useFrame } from "../api/frames";
import { useMeasurementOptions } from "../api/measurements";
import { PageLoader } from "../auth/guards";
import { Chart, type Trace } from "../data/Chart";
import {
  axisLabels,
  defaultSpectrum,
  PROCESSED_VIEWS,
  SPECTRUM_LABELS,
  VIEW_LABELS,
  type ViewKind,
} from "../data/labels";
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

// Fixed colours, so the fitted functions are recognisable in every plot.
const COLORS = {
  data: "#1c7ed6",
  preEdge: "#f08c00",
  postEdge: "#2f9e44",
  background: "#e03131",
  real: "#f08c00",
  imaginary: "#2f9e44",
  window: "#868e96",
};

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

  const [viewChoice, setView] = useState<ViewKind>("spectrum");
  const [spectrumChoice, setSpectrum] = useState<string | null>(null);
  const [channelChoice, setChannel] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  // Two merges: of all sweeps in the batch (whatever is checked) and of the checked ones.
  const [mergeAll, setMergeAll] = useState(false);
  const [mergeChecked, setMergeChecked] = useState(false);
  const [parts, setParts] = useState({ real: false, imaginary: false });

  const channels = first.channels.filter((c) => c !== "energy");
  // Without a derived spectrum only raw signals can be shown (and nothing processed).
  const view: ViewKind = first.spectra.length ? viewChoice : "raw";
  const processedView = PROCESSED_VIEWS.includes(view);
  const spectrum =
    spectrumChoice && first.spectra.includes(spectrumChoice)
      ? spectrumChoice
      : defaultSpectrum(first);
  const channel = channelChoice && channels.includes(channelChoice) ? channelChoice : channels[0];
  const name = view === "raw" ? channel : spectrum;
  const spec: CurveSpec | null =
    processedView || !name ? null : { view: view === "raw" ? "raw" : "spectrum", name };

  const shown = useMemo(() => inBatch.filter((s) => !hidden.has(s.id)), [inBatch, hidden]);
  const curves = useSweepCurves(shown, spec);
  const mergedAll = useMergedCurve(inBatch, spec, mergeAll);
  const mergedChecked = useMergedCurve(shown, spec, mergeChecked);
  // Processing input: the checked sweep, or the merge of the checked sweeps.
  const processed = useProcessed(processedView ? shown : [], spectrum);

  const traces = useMemo(() => {
    if (processedView) return processedTraces(view, processed.data, parts);
    const result: Trace[] = shown.flatMap((s, i) => {
      const data = curves.data[i];
      return data ? [{ name: `Sweep ${s.sweep_no}`, x: data.x, y: data.y }] : [];
    });
    if (mergeAll && mergedAll.data && inBatch.length > 1) {
      result.push({ name: `Merged, all (${inBatch.length})`, ...mergedAll.data, emphasis: true });
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
  }, [
    view,
    processedView,
    processed.data,
    parts,
    shown,
    inBatch,
    curves.data,
    mergeAll,
    mergedAll.data,
    mergeChecked,
    mergedChecked.data,
  ]);
  const loading = processedView
    ? processed.isLoading
    : curves.isLoading ||
      (mergeAll && mergedAll.isLoading) ||
      (mergeChecked && mergedChecked.isLoading);
  const failed = processedView
    ? processed.error
    : (curves.error ?? mergedAll.error ?? mergedChecked.error);
  const [xLabel, yLabel] = axisLabels(view, name);
  // "Merge all sweeps" does not depend on which sweeps are checked.
  const nothingToPlot = shown.length === 0 && (processedView || !(mergeAll && inBatch.length > 1));

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
          value={view}
          onChange={(value) => setView(value as ViewKind)}
          data={(["spectrum", "raw", "mu", "chi", "chir"] as const).map((v) => ({
            value: v,
            label: VIEW_LABELS[v],
            disabled: v !== "raw" && first.spectra.length === 0,
          }))}
        />
        {view !== "raw" && first.spectra.length > 0 && (
          <Select
            aria-label="Spectrum"
            data={first.spectra.map((s) => ({ value: s, label: SPECTRUM_LABELS[s] ?? s }))}
            value={spectrum ?? null}
            onChange={setSpectrum}
            allowDeselect={false}
            w={300}
          />
        )}
        {view === "raw" && (
          <Select
            aria-label="Channel"
            data={channels}
            value={channel ?? null}
            onChange={setChannel}
            allowDeselect={false}
            searchable
            w={200}
          />
        )}
        {view === "chir" && (
          <Group gap="md">
            <Checkbox
              label="Real part"
              checked={parts.real}
              onChange={(e) => setParts({ ...parts, real: e.currentTarget.checked })}
            />
            <Checkbox
              label="Imaginary part"
              checked={parts.imaginary}
              onChange={(e) => setParts({ ...parts, imaginary: e.currentTarget.checked })}
            />
          </Group>
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
                    onClick={() => setHidden(new Set(inBatch.map((s) => s.id)))}
                  >
                    None
                  </Button>
                </Group>
              </Group>
              {inBatch.map((s) => (
                <Checkbox
                  key={s.id}
                  label={`Sweep ${s.sweep_no}`}
                  checked={!hidden.has(s.id)}
                  onChange={() => toggle(s.id)}
                />
              ))}
              {processedView ? (
                <Text size="xs" c="dimmed" mt="xs">
                  {shown.length > 1
                    ? `Processing the merge of sweeps ${shown.map((s) => s.sweep_no).join(", ")}.`
                    : shown.length === 1
                      ? `Processing sweep ${shown[0]!.sweep_no}.`
                      : "Check the sweeps to process; several are merged first."}
                </Text>
              ) : (
                <>
                  <Switch
                    mt="xs"
                    label="Merge all sweeps"
                    checked={mergeAll}
                    onChange={(e) => setMergeAll(e.currentTarget.checked)}
                    disabled={inBatch.length < 2}
                  />
                  <Switch
                    label="Merge checked sweeps"
                    checked={mergeChecked}
                    onChange={(e) => setMergeChecked(e.currentTarget.checked)}
                    disabled={shown.length < 2}
                  />
                </>
              )}
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 9 }}>
          <Card withBorder pos="relative">
            {failed && <Alert color="red">{failed.message}</Alert>}
            {processedView && processed.data && processed.data.problems.length > 0 && (
              <Alert color="yellow" title="Processing incomplete" mb="sm">
                {processed.data.problems.join(" ")}
              </Alert>
            )}
            {loading && (
              <Group gap="xs" pos="absolute" top={8} right={12} style={{ zIndex: 1 }}>
                <Loader size="xs" />
                <Text size="xs" c="dimmed">
                  Loading…
                </Text>
              </Group>
            )}
            {nothingToPlot ? (
              <Text c="dimmed" ta="center" py="xl">
                {processedView
                  ? "Select at least one sweep."
                  : "Select at least one sweep, or merge all sweeps."}
              </Text>
            ) : (
              <Chart traces={traces} xLabel={xLabel} yLabel={yLabel} />
            )}
          </Card>
        </Grid.Col>
      </Grid>
      {processedView && processed.data && <ProcessingCard result={processed.data} />}
      <MetadataCard sweeps={inBatch} />
    </Stack>
  );
}

function processedTraces(
  view: ViewKind,
  data: ProcessedSpectrum | undefined,
  parts: { real: boolean; imaginary: boolean },
): Trace[] {
  if (!data) return [];
  if (view === "mu") {
    const result: Trace[] = [{ name: "μ(E)", ...data.mu, color: COLORS.data }];
    // The fitted functions are always drawn (a click on the legend hides one).
    if (data.pre_edge)
      result.push({ name: "Pre-edge", ...data.pre_edge, color: COLORS.preEdge, dashed: true });
    if (data.post_edge)
      result.push({ name: "Post-edge", ...data.post_edge, color: COLORS.postEdge, dashed: true });
    if (data.background)
      result.push({ name: "Background", ...data.background, color: COLORS.background });
    return result;
  }
  if (view === "chi") {
    if (!data.chi) return [];
    const result: Trace[] = [{ name: "k²χ(k)", ...data.chi, color: COLORS.data }];
    if (data.ft_window) {
      // The window (0..1) is scaled to the largest |k²χ(k)| so both are readable together.
      const scale = Math.max(...data.chi.y.map((v) => Math.abs(v ?? 0)), 0) || 1;
      result.push({
        name: "FT window",
        x: data.ft_window.x,
        y: data.ft_window.y.map((v) => (v === null ? null : v * scale)),
        color: COLORS.window,
      });
    }
    return result;
  }
  if (!data.chir) return [];
  const { r, magnitude, real, imaginary } = data.chir;
  const result: Trace[] = [{ name: "|χ(R)|", x: r, y: magnitude, color: COLORS.data }];
  if (parts.real) result.push({ name: "Re χ(R)", x: r, y: real, color: COLORS.real });
  if (parts.imaginary)
    result.push({ name: "Im χ(R)", x: r, y: imaginary, color: COLORS.imaginary });
  return result;
}

/** E0, edge step and the (automatic) parameters of the shown processing. */
function ProcessingCard({ result }: { result: ProcessedSpectrum }) {
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={600}>Processing</Text>
        <Grid gap="lg">
          <Grid.Col span={{ base: 12, md: 6 }}>
            <KeyValues
              values={{
                input:
                  result.sweeps.length > 1
                    ? `merge of sweeps ${result.sweeps.join(", ")}`
                    : `sweep ${result.sweeps[0]}`,
                spectrum: SPECTRUM_LABELS[result.spectrum] ?? result.spectrum,
                "E0 (eV)": `${result.e0} (${result.element} ${result.edge}, ${result.e0_source})`,
                "edge step": result.edge_step === null ? "—" : result.edge_step.toPrecision(4),
              }}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 6 }}>
            <KeyValues values={result.parameters} />
          </Grid.Col>
        </Grid>
      </Stack>
    </Card>
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
          <Text fw={600}>
            Metadata{" "}
            {detail && (
              <Badge size="xs" variant="light" color="gray">
                {detail.sweep.points} points
              </Badge>
            )}
          </Text>
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
          <KeyValues
            values={{
              ...detail.sweep.measured,
              uploaded: new Date(detail.sweep.uploaded_at).toLocaleString(),
              ...detail.metadata,
            }}
          />
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
