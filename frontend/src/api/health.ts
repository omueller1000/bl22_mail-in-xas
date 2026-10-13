import { useQuery } from "@tanstack/react-query";

import { api, type HealthResponse } from "./client";

async function fetchHealth(): Promise<HealthResponse> {
  const { data, error, response } = await api.GET("/health");
  if (data) return data;
  // 503 still carries a HealthResponse describing what is down.
  if (response.status === 503 && error) return error;
  throw new Error(`Health check failed: HTTP ${response.status}`);
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
    retry: false,
  });
}
