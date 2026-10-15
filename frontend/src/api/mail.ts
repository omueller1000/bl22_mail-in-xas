import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "./client";

const STATUS_KEY = ["mail", "status"];
const OUTBOX_KEY = ["mail", "outbox"];

export function useMailStatus() {
  return useQuery({
    queryKey: STATUS_KEY,
    queryFn: async () => unwrap(await api.GET("/admin/mail")),
  });
}

/** The latest emails; refreshed every 10 s while the page is open. */
export function useOutbox() {
  return useQuery({
    queryKey: OUTBOX_KEY,
    queryFn: async () => unwrap(await api.GET("/admin/mail/outbox")),
    refetchInterval: 10_000,
  });
}

export function useSetMailSwitches() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { enabled: boolean; redirect_to: string | null }) =>
      unwrap(await api.PUT("/admin/mail", { body })),
    onSuccess: (status) => queryClient.setQueryData(STATUS_KEY, status),
  });
}

export function useSendTestEmail() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (to: string) => {
      const { response, error } = await api.POST("/admin/mail/test", { body: { to } });
      const detail = (error as unknown as { detail?: unknown } | undefined)?.detail;
      if (!response.ok) throw new ApiError(response.status, detail);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: OUTBOX_KEY }),
  });
}
