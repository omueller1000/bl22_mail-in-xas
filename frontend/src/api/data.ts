import { type UseQueryResult, useQueries, useQuery } from "@tanstack/react-query";

import {
  api,
  API_BASE_URL,
  type DataView,
  type PlotCurve,
  type SweepInfo,
  unwrap,
} from "./client";

/** What to plot: a raw channel or a derived spectrum, by name. */
export interface CurveSpec {
  view: DataView;
  name: string;
}

// Raw data never changes, so neither do curves computed from it.
const staleTime = Infinity;

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
      staleTime,
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
    staleTime,
  });
}

/**
 * Normalisation, background, chi(k) and chi(R) of a spectrum: of one sweep, or of the merge of
 * several sweeps of one batch. Computed by the backend with automatic parameters.
 */
export function useProcessed(sweeps: SweepInfo[], spectrum: string | undefined) {
  const first = sweeps[0];
  const numbers = sweeps.map((s) => s.sweep_no);
  return useQuery({
    queryKey: ["data", "process", first?.measurement_id, first?.batch_no, numbers, spectrum],
    queryFn: async () =>
      unwrap(
        await api.GET("/measurements/{measurement_id}/batches/{batch_no}/process", {
          params: {
            path: { measurement_id: first!.measurement_id, batch_no: first!.batch_no },
            query: { spectrum: spectrum!, sweeps: numbers },
          },
        }),
      ),
    enabled: Boolean(first && spectrum),
    // An admin can change the processing parameters at any time; recomputing is cheap.
    staleTime: 30_000,
  });
}

export const exportUrl = (barcode: string) => `${API_BASE_URL}/frames/${barcode}/export.zip`;
