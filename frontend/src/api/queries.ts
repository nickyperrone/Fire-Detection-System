import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  ApiError,
  type OutlineIn,
  type SettingsIn,
  type TerritoryIn,
} from "./client";

// The worker reads fires every 5 minutes; polling at half that shows a new pass within minutes.
const REFRESH_MS = 2.5 * 60 * 1000;

/** Who is signed in, or null (docs/09-accounts-and-alerts.md). */
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.me();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: Infinity,
  });
}

export function useLogin() {
  return useMutation({
    mutationFn: ({ email, locale }: { email: string; locale: string }) =>
      api.login(email, locale),
  });
}

export function useChangeSummary() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.changeSummary,
    onSuccess: (me) => client.setQueryData(["me"], me),
  });
}

export function useSummaryNow() {
  return useMutation({ mutationFn: api.summaryNow });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.logout,
    // Everything cached belonged to the account that left.
    onSuccess: () => client.resetQueries(),
  });
}

// Field data exists only for a signed-in user; `enabled` is false while signed out.
export function usePortfolio(tags: string[], enabled = true) {
  return useQuery({
    queryKey: ["portfolio", tags],
    queryFn: () => api.portfolio(tags),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useTerritories(enabled = true) {
  return useQuery({
    queryKey: ["territories"],
    queryFn: api.territories,
    enabled,
  });
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
    client.invalidateQueries({ queryKey: ["tags"] });
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

export function useChangeSettings() {
  const invalidate = useInvalidateTerritories();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: SettingsIn }) =>
      api.changeSettings(id, body),
    onSuccess: invalidate,
  });
}

export function useTags(enabled = true) {
  return useQuery({ queryKey: ["tags"], queryFn: api.tags, enabled });
}

export function useReplaceTags() {
  const invalidate = useInvalidateTerritories();
  return useMutation({
    mutationFn: ({ id, tags }: { id: number; tags: string[] }) =>
      api.replaceTags(id, tags),
    onSuccess: invalidate,
  });
}

export function useSetTagColor() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, color }: { id: number; color: string }) =>
      api.setTagColor(id, color),
    onSuccess: () => client.invalidateQueries({ queryKey: ["tags"] }),
  });
}

export function useDeleteTerritory() {
  const invalidate = useInvalidateTerritories();
  return useMutation({
    mutationFn: api.deleteTerritory,
    onSuccess: invalidate,
  });
}
