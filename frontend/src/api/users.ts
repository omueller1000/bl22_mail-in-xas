import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { SortOrder } from "../components/paging";
import { api, type Role, unwrap } from "./client";

const USERS_KEY = ["users"];

export type UserSort = "name" | "affiliation";

/** One page of users (Operators), searched and sorted on the server. */
export function useUsers(params: {
  page: number;
  page_size: number;
  sort: UserSort;
  order: SortOrder;
  q?: string;
  role?: Role;
}) {
  return useQuery({
    queryKey: [...USERS_KEY, params],
    queryFn: async () => unwrap(await api.GET("/users", { params: { query: params } })),
    placeholderData: keepPreviousData,
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
