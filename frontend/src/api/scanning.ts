import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type ScanAction, unwrap } from "./client";

const STORAGE_KEY = ["storage", "internal"];
const WARNINGS_KEY = ["warnings"];

/** After a frame moves, everything that lists frames may be outdated. */
function useRefreshAfterMove() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["frames"] }),
      queryClient.invalidateQueries({ queryKey: STORAGE_KEY }),
      queryClient.invalidateQueries({ queryKey: WARNINGS_KEY }),
    ]);
}

/** Scanned frames with what each action would do to them (changes nothing). */
export async function lookupScan(barcodes: string[]) {
  return unwrap(await api.POST("/scans/lookup", { body: { barcodes } }));
}

export function useApplyScan() {
  const refresh = useRefreshAfterMove();
  return useMutation({
    mutationFn: async ({ action, barcodes }: { action: ScanAction; barcodes: string[] }) =>
      unwrap(await api.POST("/scans/apply", { body: { action, barcodes } })),
    onSuccess: refresh,
  });
}

export function useStoreInternally() {
  const refresh = useRefreshAfterMove();
  return useMutation({
    mutationFn: async ({
      barcode,
      container,
      slot,
    }: {
      barcode: string;
      container: number;
      slot: number;
    }) =>
      unwrap(
        await api.POST("/frames/{barcode}/internal-storage", {
          params: { path: { barcode } },
          body: { container, slot },
        }),
      ),
    onSuccess: refresh,
  });
}

export function useRelease() {
  const refresh = useRefreshAfterMove();
  return useMutation({
    mutationFn: async (barcode: string) =>
      unwrap(await api.POST("/frames/{barcode}/release", { params: { path: { barcode } } })),
    onSuccess: refresh,
  });
}

export function useInternalStorage() {
  return useQuery({
    queryKey: STORAGE_KEY,
    queryFn: async () => unwrap(await api.GET("/storage/internal")),
  });
}

/** Own frames needing attention; Operators may ask for everyone's. */
export function useWarnings(allUsers = false) {
  return useQuery({
    queryKey: [...WARNINGS_KEY, { allUsers }],
    queryFn: async () =>
      unwrap(await api.GET("/warnings", { params: { query: { all_users: allUsers } } })),
  });
}
