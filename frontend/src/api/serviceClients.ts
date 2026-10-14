import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "./client";

const KEY = ["service-clients"];

export function useServiceClients() {
  return useQuery({
    queryKey: KEY,
    queryFn: async () => unwrap(await api.GET("/service-clients")),
  });
}

function useClientMutation<T, R>(mutationFn: (args: T) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn, onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }) });
}

export function useCreateServiceClient() {
  return useClientMutation(async (name: string) =>
    unwrap(await api.POST("/service-clients", { body: { name } })),
  );
}

/** Returns the new key; it is shown only this once. */
export function useCreateKey() {
  return useClientMutation(async (clientId: string) =>
    unwrap(
      await api.POST("/service-clients/{client_id}/keys", {
        params: { path: { client_id: clientId } },
      }),
    ),
  );
}

export function useRevokeKey() {
  return useClientMutation(async ({ clientId, keyId }: { clientId: string; keyId: string }) =>
    unwrap(
      await api.DELETE("/service-clients/{client_id}/keys/{key_id}", {
        params: { path: { client_id: clientId, key_id: keyId } },
      }),
    ),
  );
}
