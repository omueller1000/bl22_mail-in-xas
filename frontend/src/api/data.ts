import { type UseQueryResult, useQueries, useQuery } from "@tanstack/react-query";

import {
  api,
  API_BASE_URL,
  type DataView,
  type PlotCurve,
  type SweepInfo,
  unwrap,
} from "./client";

/** What to plot: a view, plus the channel or spectrum name for "raw" and "spectrum". */
export interface CurveSpec {
  view: DataView;
  name?: string;
}

// Raw data never changes; processed data can be replaced by the control software.
const staleTime = (view: DataView) => (view === "raw" || view === "spectrum" ? Infinity : 60_000);

export function useFrameSweeps(barcode: string) {
  return useQuery({
    queryKey: ["data", "sweeps", barcode],
    queryFn: async () =>
      unwrap(await api.GET("/frames/{barcode}/sweeps", { params: { path: { barcode } } })),
  });
}

export function useSweepDetail(sweepId: string | null) {
  return useQuery({
    queryKey: ["data", "sweep", sweepId],
    queryFn: async () =>
      unwrap(
        await api.GET("/sweeps/{sweep_id}", { params: { path: { sweep_id: sweepId ?? "" } } }),
      ),
    enabled: Boolean(sweepId),
  });
}

// Stable across renders, so the combined result only changes when a curve does.
function combineCurves(results: UseQueryResult<PlotCurve>[]) {
  return {
    data: results.map((r) => r.data),
    isLoading: results.some((r) => r.isLoading),
    error: results.find((r) => r.error)?.error ?? null,
  };
}

/** One curve per sweep, each loaded on its own (only when shown). */
export function useSweepCurves(sweeps: SweepInfo[], spec: CurveSpec | null) {
  return useQueries({
    combine: combineCurves,
    queries: sweeps.map((sweep) => ({
      queryKey: ["data", "curve", sweep.id, spec?.view, spec?.name],
      queryFn: async () =>
        unwrap(
          await api.GET("/sweeps/{sweep_id}/curve", {
            params: { path: { sweep_id: sweep.id }, query: { view: spec!.view, name: spec!.name } },
          }),
        ),
      enabled: Boolean(spec),
      staleTime: spec ? staleTime(spec.view) : 0,
    })),
  });
}

/** The average of the given sweeps of one batch (computed by the backend, not stored). */
export function useMergedCurve(sweeps: SweepInfo[], spec: CurveSpec | null, enabled: boolean) {
  const first = sweeps[0];
  const numbers = sweeps.map((s) => s.sweep_no);
  return useQuery({
    queryKey: ["data", "merge", first?.measurement_id, first?.batch_no, numbers, spec],
    queryFn: async () =>
      unwrap(
        await api.GET("/measurements/{measurement_id}/batches/{batch_no}/merge", {
          params: {
            path: { measurement_id: first!.measurement_id, batch_no: first!.batch_no },
            query: { view: spec!.view, name: spec!.name, sweeps: numbers },
          },
        }),
      ),
    enabled: enabled && Boolean(spec) && sweeps.length > 1,
    staleTime: spec ? staleTime(spec.view) : 0,
  });
}

export const exportUrl = (barcode: string) => `${API_BASE_URL}/frames/${barcode}/export.zip`;
