import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type TerritoryIn } from "./client";

// Fires are ingested every 15 minutes and the forecast every hour; polling faster adds nothing.
const FIVE_MINUTES = 5 * 60 * 1000;

export function usePortfolio(tags: string[]) {
  return useQuery({
    queryKey: ["portfolio", tags],
    queryFn: () => api.portfolio(tags),
    refetchInterval: FIVE_MINUTES,
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

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: FIVE_MINUTES });
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

export function useDeleteTerritory() {
  const invalidate = useInvalidateTerritories();
  return useMutation({ mutationFn: api.deleteTerritory, onSuccess: invalidate });
}
