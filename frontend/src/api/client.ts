import type { components } from "./schema";

type Schemas = components["schemas"];
export type PortfolioEntry = Schemas["PortfolioEntryOut"];
export type FireAnswer = Schemas["FireAnswerOut"];
export type SprayAnswer = Schemas["SprayAnswerOut"];
export type LightningAnswer = Schemas["LightningAnswerOut"];
export type Territory = Schemas["TerritoryOut"];
export type TerritoryIn = Schemas["TerritoryIn"];
export type RiskEvent = Schemas["RiskEventOut"];
export type SprayHour = Schemas["SprayHourOut"];
export type Health = Schemas["HealthOut"];
export type FireHistory = Schemas["FireHistoryOut"];
export type ForecastAnswer = Schemas["ForecastAnswerOut"];
export type ForecastDay = Schemas["ForecastDayOut"];
export type DataQuality = Schemas["DataQuality"];
export type Severity = Schemas["Severity"];
export type SprayStatus = Schemas["SprayStatus"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** Stable code for validation errors (e.g. "outside_country"), translated by the UI. */
    readonly code: string | null = null,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail =
      typeof body?.detail === "string" ? body.detail : response.statusText;
    throw new ApiError(
      response.status,
      detail,
      typeof body?.code === "string" ? body.code : null,
    );
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

function tagQuery(tags: string[]): string {
  const params = new URLSearchParams();
  tags.forEach((tag) => params.append("tag", tag));
  return params.size ? `?${params}` : "";
}

export const api = {
  portfolio: (tags: string[]) =>
    request<PortfolioEntry[]>(`/portfolio${tagQuery(tags)}`),
  territories: () => request<Territory[]>("/territories"),
  createTerritory: (body: TerritoryIn) =>
    request<Territory>("/territories", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteTerritory: (id: number) =>
    request<void>(`/territories/${id}`, { method: "DELETE" }),
  riskEvents: (id: number) =>
    request<RiskEvent[]>(`/territories/${id}/risk-events`),
  sprayConditions: (id: number) =>
    request<SprayHour[]>(`/territories/${id}/spray-conditions`),
  health: () => request<Health>("/health"),
  boundary: () =>
    request<GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon>>(
      "/boundary",
    ),
  fireHistory: (id: number) =>
    request<FireHistory>(`/territories/${id}/fire-history`),
};

export function tileUrl(layer: string, version = 0): string {
  // MapLibre fetches tiles from a web worker, which needs an absolute URL.
  return `${window.location.origin}/api/tiles/${layer}/{z}/{x}/{y}.pbf?v=${version}`;
}
