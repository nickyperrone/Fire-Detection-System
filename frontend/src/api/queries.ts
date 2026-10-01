import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type OutlineIn, type TerritoryIn } from "./client";

// The worker reads fires every 5 minutes; polling at half that shows a new pass within minutes.
const REFRESH_MS = 2.5 * 60 * 1000;

export function usePortfolio(tags: string[]) {
  return useQuery({
    queryKey: ["portfolio", tags],
    queryFn: () => api.portfolio(tags),
    refetchInterval: REFRESH_MS,
  });
}

export function useTerritories() {
  return useQuery({ queryKey: ["territories"], queryFn: api.territories });
}

export function useRiskEvents(id: number | null) {
  return useQuery({
    queryKey: ["risk-events", id],
    queryFn: () => api.riskEvents(id!),
    enabled: id !== null,
  });
}

export function useSprayConditions(id: number | null) {
  return useQuery({
    queryKey: ["spray-conditions", id],
    queryFn: () => api.sprayConditions(id!),
    enabled: id !== null,
  });
}

export function useFireHistory(id: number) {
  // The archive changes once a year; no refetching while the app is open.
  return useQuery({
    queryKey: ["fire-history", id],
    queryFn: () => api.fireHistory(id),
    staleTime: Infinity,
  });
}

export function useBoundary() {
  // A country's outline does not change while the app is open.
  return useQuery({
    queryKey: ["boundary"],
    queryFn: api.boundary,
    staleTime: Infinity,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: REFRESH_MS,
  });
}

function useInvalidateTerritories() {
  const client = useQueryClient();
  return () => {
    client.invalidateQueries({ queryKey: ["territories"] });
    client.invalidateQueries({ queryKey: ["portfolio"] });
  };
}

export function useCreateTerritory() {
  const invalidate = useInvalidateTerritories();
  return useMutation({
    mutationFn: (body: TerritoryIn) => api.createTerritory(body),
    onSuccess: invalidate,
  });
}

/** The field as it would be after the edit, with any problem, before saving it. */
export function useOutlinePreview(
  id: number,
  operation: OutlineIn["operation"],
  piece: Record<string, unknown> | null,
) {
  return useQuery({
    queryKey: ["outline-preview", id, operation, piece],
    queryFn: () =>
      api.editOutline(id, {
        operation,
        geometry: piece!,
        preview: true,
      }),
    enabled: piece !== null,
    retry: false,
  });
}

export function useEditOutline() {
  const client = useQueryClient();
  const invalidate = useInvalidateTerritories();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: OutlineIn }) =>
      api.editOutline(id, body),
    onSuccess: (_, { id }) => {
      invalidate();
      client.invalidateQueries({ queryKey: ["risk-events", id] });
    },
  });
}

export function useDeleteTerritory() {
  const invalidate = useInvalidateTerritories();
  return useMutation({
    mutationFn: api.deleteTerritory,
    onSuccess: invalidate,
  });
}
