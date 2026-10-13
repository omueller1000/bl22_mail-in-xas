import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Frame, unwrap } from "./client";

const frameKey = (barcode: string) => ["frames", "detail", barcode];

export function useFrame(barcode: string) {
  return useQuery({
    queryKey: frameKey(barcode),
    queryFn: async () =>
      unwrap(await api.GET("/frames/{barcode}", { params: { path: { barcode } } })),
  });
}

/** Mutations return the updated frame; put it in the cache and refresh dependent lists. */
function useFrameMutation<T>(barcode: string, mutationFn: (args: T) => Promise<Frame>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: (frame) => {
      queryClient.setQueryData(frameKey(barcode), frame);
      void queryClient.invalidateQueries({ queryKey: ["frames"], exact: false });
      void queryClient.invalidateQueries({ queryKey: ["samples"] });
    },
    // e.g. "changed elsewhere": reload, so the user sees the current state
    onError: () => queryClient.invalidateQueries({ queryKey: frameKey(barcode) }),
  });
}

export function useSetPlates(frame: Frame) {
  return useFrameMutation(frame.barcode, async (plates: { left: string | null; right: string | null }) =>
    unwrap(
      await api.PUT("/frames/{barcode}/plates", {
        params: { path: { barcode: frame.barcode } },
        body: { version: frame.version, ...plates },
      }),
    ),
  );
}

export function useSetNote(frame: Frame) {
  return useFrameMutation(frame.barcode, async (note: string) =>
    unwrap(
      await api.PUT("/frames/{barcode}/note", {
        params: { path: { barcode: frame.barcode } },
        body: { version: frame.version, note },
      }),
    ),
  );
}

export function useAssignSample(frame: Frame) {
  return useFrameMutation(frame.barcode, async ({ position, sampleId }: { position: string; sampleId: string }) =>
    unwrap(
      await api.PUT("/frames/{barcode}/positions/{position}", {
        params: { path: { barcode: frame.barcode, position } },
        body: { version: frame.version, sample_id: sampleId },
      }),
    ),
  );
}

export function useClearPosition(frame: Frame) {
  return useFrameMutation(frame.barcode, async (position: string) =>
    unwrap(
      await api.DELETE("/frames/{barcode}/positions/{position}", {
        params: { path: { barcode: frame.barcode, position }, query: { version: frame.version } },
      }),
    ),
  );
}
