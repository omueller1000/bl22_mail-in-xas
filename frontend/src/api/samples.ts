import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, API_BASE_URL, ApiError, type Sample, unwrap } from "./client";

const SAMPLES_KEY = ["samples"];

export const MSDS_MAX_BYTES = 1024 * 1024;

/** Own samples, newest first; archived ones only if asked for. */
export function useSamples(includeArchived = false) {
  return useQuery({
    queryKey: [...SAMPLES_KEY, { includeArchived }],
    queryFn: async () =>
      unwrap(await api.GET("/samples", { params: { query: { include_archived: includeArchived } } })),
  });
}

function useSampleMutation<T>(mutationFn: (args: T) => Promise<Sample | void>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SAMPLES_KEY }),
  });
}

export function useCreateSample() {
  return useSampleMutation(async (body: { name: string; description: string }) =>
    unwrap(await api.POST("/samples", { body })),
  );
}

export function useUpdateSample() {
  return useSampleMutation(
    async ({ id, ...body }: { id: string; name: string; description: string }) =>
      unwrap(await api.PUT("/samples/{sample_id}", { params: { path: { sample_id: id } }, body })),
  );
}

export function useSetArchived() {
  return useSampleMutation(async ({ id, archived }: { id: string; archived: boolean }) =>
    unwrap(
      await api.PUT("/samples/{sample_id}/archived", {
        params: { path: { sample_id: id } },
        body: { archived },
      }),
    ),
  );
}

export function useDeleteSample() {
  return useSampleMutation(async (id: string) => {
    const { response, error } = await api.DELETE("/samples/{sample_id}", {
      params: { path: { sample_id: id } },
    });
    if (!response.ok) throw new ApiError(response.status, (error as { detail?: unknown })?.detail);
  });
}

export function useUploadMsds() {
  return useSampleMutation(async ({ id, file }: { id: string; file: File }) => {
    const form = new FormData();
    form.append("file", file);
    return unwrap(
      await api.PUT("/samples/{sample_id}/msds", {
        params: { path: { sample_id: id } },
        // Let the browser set the multipart content type (with boundary).
        body: form as never,
        bodySerializer: () => form,
      }),
    );
  });
}

export function useDeleteMsds() {
  return useSampleMutation(async (id: string) =>
    unwrap(await api.DELETE("/samples/{sample_id}/msds", { params: { path: { sample_id: id } } })),
  );
}

/** Link that downloads the MSDS (a plain navigation; the session cookie authenticates it). */
export function msdsUrl(sampleId: string): string {
  return `${API_BASE_URL}/samples/${sampleId}/msds`;
}
