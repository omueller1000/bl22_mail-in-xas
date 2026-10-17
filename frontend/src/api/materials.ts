import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { SortOrder } from "../components/paging";
import {
  api,
  type FrameState,
  type MaterialRequestCreate,
  type RequestState,
  unwrap,
} from "./client";

const KEYS = {
  plateTypes: ["plate-types"],
  requests: ["material-requests"],
  frames: ["frames"],
  shipping: ["frames", "shipping"],
};

export function usePlateTypes() {
  return useQuery({
    queryKey: KEYS.plateTypes,
    queryFn: async () => unwrap(await api.GET("/plate-types")),
    staleTime: Infinity, // fixed catalog
  });
}

/** Own requests, optionally filtered by state. */
export function useMaterialRequests(options: { state?: RequestState } = {}) {
  const query = { state: options.state };
  return useQuery({
    queryKey: [...KEYS.requests, query],
    queryFn: async () => unwrap(await api.GET("/material-requests", { params: { query } })),
  });
}

/** One page of all users' requests (Operators). */
export function useAllMaterialRequests(params: {
  page: number;
  page_size: number;
  sort: "number";
  order: SortOrder;
  q?: string;
  state?: RequestState;
}) {
  return useQuery({
    queryKey: [...KEYS.requests, "all", params],
    queryFn: async () =>
      unwrap(await api.GET("/material-requests/all", { params: { query: params } })),
    placeholderData: keepPreviousData,
  });
}

export function useMaterialRequest(id: string) {
  return useQuery({
    queryKey: [...KEYS.requests, id],
    queryFn: async () =>
      unwrap(
        await api.GET("/material-requests/{request_id}", {
          params: { path: { request_id: id } },
        }),
      ),
  });
}

export function useCreateRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: MaterialRequestCreate) =>
      unwrap(await api.POST("/material-requests", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEYS.requests }),
  });
}

export function useIssueBarcodes() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, barcodes }: { id: string; barcodes: string[] }) =>
      unwrap(
        await api.POST("/material-requests/{request_id}/issue", {
          params: { path: { request_id: id } },
          body: { barcodes },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: KEYS.requests });
      void queryClient.invalidateQueries({ queryKey: KEYS.frames });
    },
  });
}

export function useRejectRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, reason }: { id: string; reason: string | null }) =>
      unwrap(
        await api.POST("/material-requests/{request_id}/reject", {
          params: { path: { request_id: id } },
          body: { reason },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEYS.requests }),
  });
}

/** Own frames, or (Operators, `allUsers`) all frames, optionally filtered by state. */
export function useFrames(options: { allUsers?: boolean; state?: FrameState } = {}) {
  const query = { all_users: options.allUsers ?? false, state: options.state };
  return useQuery({
    queryKey: [...KEYS.frames, query],
    queryFn: async () => unwrap(await api.GET("/frames", { params: { query } })),
  });
}

/** One page of all users' frames (Operators); reserved barcodes only with that state. */
export function useAllFrames(params: {
  page: number;
  page_size: number;
  sort: "barcode";
  order: SortOrder;
  q?: string;
  state?: FrameState;
}) {
  return useQuery({
    queryKey: [...KEYS.frames, "all", params],
    queryFn: async () => unwrap(await api.GET("/frames/all", { params: { query: params } })),
    placeholderData: keepPreviousData,
  });
}

/** Look up one frame (used to check scanned barcodes). Resolves to null if unknown. */
export async function fetchFrame(barcode: string) {
  const result = await api.GET("/frames/{barcode}", { params: { path: { barcode } } });
  if (result.response.status === 404) return null;
  return unwrap(result);
}

export function useReserveBarcodes() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (count: number) =>
      unwrap(await api.POST("/frames/reserve", { body: { count } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEYS.frames }),
  });
}

export function useShippingList() {
  return useQuery({
    queryKey: KEYS.shipping,
    queryFn: async () => unwrap(await api.GET("/frames/shipping")),
  });
}

export function useMarkShipped() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (barcodes: string[]) =>
      unwrap(await api.POST("/frames/ship", { body: { barcodes } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: KEYS.frames });
      void queryClient.invalidateQueries({ queryKey: KEYS.requests });
    },
  });
}
