import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, type Frame, type MeasurementInput, unwrap } from "./client";

const measurementsKey = (barcode: string) => ["frames", "measurements", barcode];
const frameKey = (barcode: string) => ["frames", "detail", barcode];

export function useMeasurementOptions() {
  return useQuery({
    queryKey: ["measurement-options"],
    queryFn: async () => unwrap(await api.GET("/measurement-options")),
    staleTime: 5 * 60_000, // admins may change the beamline's energy range
  });
}

export function useMeasurements(barcode: string) {
  return useQuery({
    queryKey: measurementsKey(barcode),
    queryFn: async () =>
      unwrap(await api.GET("/frames/{barcode}/measurements", { params: { path: { barcode } } })),
  });
}

/**
 * Measurement, safety and lock changes bump the frame's version. Wait for the frame and its
 * measurements to reload before the mutation counts as done, so the next change uses the new
 * version.
 */
function useFrameChange<T, R>(frame: Frame, mutationFn: (args: T) => Promise<R>) {
  const queryClient = useQueryClient();
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: frameKey(frame.barcode) }),
      queryClient.invalidateQueries({ queryKey: measurementsKey(frame.barcode) }),
      queryClient.invalidateQueries({ queryKey: ["frames"] }),
      queryClient.invalidateQueries({ queryKey: ["samples"] }),
    ]);
  return useMutation({ mutationFn, onSuccess: refresh, onError: refresh });
}

type Settings = Omit<MeasurementInput, "version">;

export function useAddMeasurement(frame: Frame) {
  return useFrameChange(frame, async ({ position, ...settings }: Settings & { position: string }) =>
    unwrap(
      await api.POST("/frames/{barcode}/positions/{position}/measurements", {
        params: { path: { barcode: frame.barcode, position } },
        body: { version: frame.version, ...settings },
      }),
    ),
  );
}

export function useUpdateMeasurement(frame: Frame) {
  return useFrameChange(frame, async ({ id, ...settings }: Settings & { id: string }) =>
    unwrap(
      await api.PUT("/measurements/{measurement_id}", {
        params: { path: { measurement_id: id } },
        body: { version: frame.version, ...settings },
      }),
    ),
  );
}

export function useDeleteMeasurement(frame: Frame) {
  return useFrameChange(frame, async (id: string) => {
    const { response, error } = await api.DELETE("/measurements/{measurement_id}", {
      params: { path: { measurement_id: id }, query: { version: frame.version } },
    });
    if (!response.ok) throw new ApiError(response.status, (error as { detail?: unknown })?.detail);
  });
}

export function useDeclareSafe(frame: Frame) {
  return useFrameChange(frame, async () =>
    unwrap(
      await api.POST("/frames/{barcode}/declare-safe", {
        params: { path: { barcode: frame.barcode } },
        body: { version: frame.version, confirm: true },
      }),
    ),
  );
}

export function useSetLocked(frame: Frame) {
  return useFrameChange(frame, async (locked: boolean) => {
    const params = { path: { barcode: frame.barcode } };
    const body = { version: frame.version };
    return unwrap(
      locked
        ? await api.POST("/frames/{barcode}/lock", { params, body })
        : await api.POST("/frames/{barcode}/unlock", { params, body }),
    );
  });
}
