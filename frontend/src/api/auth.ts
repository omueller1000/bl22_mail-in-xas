import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, API_BASE_URL, type Me, type Profile, type Registration, type Role, unwrap } from "./client";

const ME_KEY = ["me"];

/** Who is logged in: anonymous, registration required, or authenticated (with the user). */
export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async () => unwrap(await api.GET("/auth/me")),
    staleTime: 60_000,
  });
}

/** URL that starts the ORCID login (a full page navigation, not a fetch). */
export function orcidLoginUrl(returnTo: string): string {
  return `${API_BASE_URL}/auth/orcid/login?return_to=${encodeURIComponent(returnTo)}`;
}

export function useDevLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { orcid: string; name?: string | null; role?: Role | null }) =>
      unwrap(await api.POST("/auth/dev-login", { body })),
    onSuccess: (me: Me) => {
      queryClient.clear(); // nothing cached from a previous user may survive
      queryClient.setQueryData(ME_KEY, me);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { response } = await api.POST("/auth/logout");
      if (!response.ok) throw new Error(`Logout failed (HTTP ${response.status})`);
    },
    onSuccess: () => {
      queryClient.clear();
      void queryClient.invalidateQueries({ queryKey: ME_KEY });
    },
  });
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Registration) => unwrap(await api.POST("/users", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_KEY }),
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Profile) => unwrap(await api.PUT("/users/me", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_KEY }),
  });
}
