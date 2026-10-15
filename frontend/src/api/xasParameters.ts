import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";

const KEY = ["xas-parameters"];

export function useXasParameters() {
  return useQuery({
    queryKey: KEY,
    queryFn: async () => unwrap(await api.GET("/admin/xas-parameters")),
  });
}

/** After a change, every processing result may differ. */
function useParameterChange<T>(mutationFn: (args: T) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async (listing) => {
      queryClient.setQueryData(KEY, listing);
      await queryClient.invalidateQueries({ queryKey: ["data", "process"] });
    },
  });
}

export function useSetXasParameters() {
  return useParameterChange(async (values: Record<string, number | null>) =>
    unwrap(await api.PUT("/admin/xas-parameters", { body: { values } })),
  );
}

export function useRestoreXasParameters() {
  return useParameterChange(async () => unwrap(await api.DELETE("/admin/xas-parameters")));
}
