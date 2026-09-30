const LOCAL_TZ = "America/Argentina/Buenos_Aires";

export function formatAge(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "unknown";
  const minutes = Math.floor((now.getTime() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 48 * 60) return `${Math.floor(minutes / 60)} h ago`;
  return `${Math.floor(minutes / 1440)} d ago`;
}

export function formatKm(meters: number | null | undefined): string {
  if (meters === null || meters === undefined) return "";
  if (meters === 0) return "inside";
  return meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1)} km`;
}

export function formatHectares(hectares: number): string {
  return `${Math.round(hectares).toLocaleString("en-US")} ha`;
}

export function localTime(iso: string, withDay = false): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: LOCAL_TZ,
    hour: "2-digit",
    minute: "2-digit",
    ...(withDay ? { weekday: "short" } : {}),
  }).format(new Date(iso));
}

export function localHourNumber(iso: string): number {
  return Number(
    new Intl.DateTimeFormat("en-GB", { timeZone: LOCAL_TZ, hour: "2-digit", hourCycle: "h23" }).format(
      new Date(iso),
    ),
  );
}
