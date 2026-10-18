import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";

const KEY = ["beamline"];

export function useBeamline() {
  return useQuery({
    queryKey: KEY,
    queryFn: async () => unwrap(await api.GET("/admin/beamline")),
  });
}

/** After a change, the measurable elements and edges differ. */
function useBeamlineChange<T>(mutationFn: (args: T) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async (settings) => {
      queryClient.setQueryData(KEY, settings);
      await queryClient.invalidateQueries({ queryKey: ["measurement-options"] });
    },
  });
}

export function useSetBeamline() {
  return useBeamlineChange(async (body: { energy_min: number; energy_max: number }) =>
    unwrap(await api.PUT("/admin/beamline", { body })),
  );
}

export function useRestoreBeamline() {
  return useBeamlineChange(async () => unwrap(await api.DELETE("/admin/beamline")));
}
