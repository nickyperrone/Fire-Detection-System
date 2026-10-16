import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  ApiError,
  type Me,
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
    meta: { inline: true },
    mutationFn: ({
      email,
      locale,
      captcha,
    }: {
      email: string;
      locale: string;
      captcha: string | null;
    }) => api.login(email, locale, captcha),
  });
}

/** Whether sign-in shows Cloudflare's check, and its public key (docs/09#bots). */
export function useAuthConfig() {
  return useQuery({
    queryKey: ["auth-config"],
    queryFn: api.authConfig,
    staleTime: Infinity,
  });
}

export function useChangeSummary() {
  const client = useQueryClient();
  return useMutation({
    meta: { inline: true },
    mutationFn: api.changeSummary,
    onSuccess: (me) => client.setQueryData(["me"], me),
  });
}

export function useChangeNotifications() {
  const client = useQueryClient();
  return useMutation({
    meta: { inline: true },
    mutationFn: api.changeNotifications,
    // At once, so a chip answers the tap without waiting for the server.
    onMutate: (notifications) => {
      const me = client.getQueryData<Me>(["me"]);
      if (me) client.setQueryData(["me"], { ...me, notifications });
    },
    onSuccess: (me) => client.setQueryData(["me"], me),
    onError: () => client.invalidateQueries({ queryKey: ["me"] }),
  });
}

export function useConnectTelegram() {
  return useMutation({
    meta: { inline: true },
    mutationFn: api.connectTelegram,
  });
}

export function useDisconnectTelegram() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.disconnectTelegram,
    onSuccess: (me) => client.setQueryData(["me"], me),
  });
}

export function useSummaryNow() {
  return useMutation({
    meta: { inline: true },
    mutationFn: api.summaryNow,
  });
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

/** The selected field's unusual patches, drawn on the map while its card is open. */
export function useAnomalyPatches(id: number | null) {
  return useQuery({
    queryKey: ["anomalies", id],
    queryFn: () => api.anomalies(id!),
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

/** A field's satellite photos; a lot answers with its field's (docs/12-field-page.md). */
export function useSnapshots(id: number) {
  return useQuery({
    queryKey: ["snapshots", id],
    queryFn: () => api.snapshots(id),
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

// Places are searched from this many letters, as the API does.
const PLACE_MIN_LETTERS = 3;

/** "Gualeguaychú" and "gualeguaychu" are the same place. */
const plain = (name: string) =>
  name.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

/** Towns, streets and addresses in Argentina for the search box (docs/04-frontend.md). Towns
 * come fast and show at once; streets, from a slower service, join when they arrive. */
export function usePlaces(query: string) {
  const q = query.trim();
  const enabled = q.length >= PLACE_MIN_LETTERS;
  const towns = useQuery({
    queryKey: ["places", "towns", q.toLowerCase()],
    queryFn: () => api.places(q, "towns"),
    enabled,
    staleTime: Infinity,
  });
  const streets = useQuery({
    queryKey: ["places", "streets", q.toLowerCase()],
    queryFn: () => api.places(q, "streets"),
    enabled,
    staleTime: Infinity,
    retry: false,
  });
  const known = new Set((towns.data ?? []).map((p) => plain(p.name)));
  const data = [
    ...(towns.data ?? []),
    // A town the street search also found is shown once.
    ...(streets.data ?? []).filter(
      (p) => !(p.bbox && known.has(plain(p.name))),
    ),
  ];
  return {
    data: towns.data || streets.data ? data : undefined,
    // "Searching" only until there is something to show.
    isFetching: data.length === 0 && (towns.isFetching || streets.isFetching),
  };
}

/** The clouds and rain layer's scan, checked every few minutes while it is on. */
export function useWeatherLayer(enabled: boolean) {
  return useQuery({
    queryKey: ["weather-layer"],
    queryFn: api.weatherLayer,
    enabled,
    refetchInterval: 5 * 60 * 1000,
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
    meta: { inline: true },
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
    meta: { inline: true },
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
