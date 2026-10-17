import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";

export function useSystemStatus() {
  return useQuery({
    queryKey: ["admin", "status"],
    queryFn: async () => unwrap(await api.GET("/admin/status")),
  });
}
