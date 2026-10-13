import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Role, unwrap } from "./client";

const USERS_KEY = ["users"];

export function useUsers() {
  return useQuery({
    queryKey: USERS_KEY,
    queryFn: async () => unwrap(await api.GET("/users")),
  });
}

export function useSetRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, role }: { userId: string; role: Role }) =>
      unwrap(
        await api.PUT("/users/{user_id}/role", {
          params: { path: { user_id: userId } },
          body: { role },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: USERS_KEY }),
  });
}
