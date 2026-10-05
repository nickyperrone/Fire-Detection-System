"use client";

import { useFireHistory } from "@/api/queries";
import { useLocale } from "@/i18n/LocaleProvider";
import type { Messages } from "@/i18n/messages";
import { formatDistance } from "@/i18n/text";
import { TONE_HEX } from "@/lib/status";

function monthName(t: Messages, month: number): string {
  return new Intl.DateTimeFormat(t.intl, {
    month: "short",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(2000, month, 1)));
}

function longDate(t: Messages, day: string): string {
  return new Intl.DateTimeFormat(t.intl, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${day}T00:00:00Z`));
}

/** Fire days near the field per year and per month (docs/07-fire-history.md). */
export function FireHistory({ territoryId }: { territoryId: number }) {
  const { t } = useLocale();
  const { data: history, isError } = useFireHistory(territoryId);
  if (isError) return <p className="text-sm text-bad">{t.app.apiDown}</p>;
  if (!history)
    return <div className="h-40 animate-pulse rounded-2xl bg-white/5" />;
  if (history.years_loaded.length === 0)
    return <p className="text-sm text-slate-400">{t.history.noData}</p>;

  const years = Object.entries(history.days_per_year).map(([year, days]) => ({
    year: Number(year),
    days,
  }));
  const yearMax = Math.max(1, ...years.map((y) => y.days));
  const monthMax = Math.max(1, ...history.days_per_month);
  const topMonths = history.days_per_month
    .map((days, month) => ({ days, month }))
    .filter((m) => m.days > 0)
    .sort((a, b) => b.days - a.days)
    .slice(0, 2)
    .map((m) => monthName(t, m.month));
  const span = years.length;

  return (
    <div className="space-y-3">
      <p
        className={`font-medium ${history.fire_days ? "text-bad" : "text-slate-200"}`}
      >
        {history.fire_days === 0
          ? t.history.none(span, history.radius_m / 1000)
          : t.history.summary(span, history.fire_days, history.radius_m / 1000)}
      </p>
      {history.fire_days > 0 && (
        <ul className="space-y-0.5 text-sm text-slate-300">
          {topMonths.length > 0 && <li>{t.history.months(topMonths)}</li>}
          {history.nearest && (
            <li>
              {t.history.nearest(
                formatDistance(t, history.nearest.distance_m),
                longDate(t, history.nearest.day),
              )}
            </li>
          )}
          {history.latest && (
            <li>{t.history.latest(longDate(t, history.latest.day))}</li>
          )}
          <li>
            {history.inside_days
              ? t.history.inside(history.inside_days)
              : t.history.neverInside}
          </li>
        </ul>
      )}

      <div>
        <p className="mb-1 text-[11px] uppercase tracking-wide text-muted">
          {t.history.perYear}
        </p>
        <div
          className="flex h-16 items-end gap-1"
          role="img"
          aria-label={t.history.perYear}
        >
          {years.map(({ year, days }) => (
            <div key={year} className="flex flex-1 flex-col items-center gap-1">
              <span className="text-[10px] text-slate-400">{days || ""}</span>
              <div
                className="w-full rounded-sm"
                title={`${year}: ${days}`}
                style={{
                  height: `${Math.max(2, (days / yearMax) * 40)}px`,
                  background: days ? TONE_HEX.bad : "rgb(255 255 255 / 0.08)",
                }}
              />
            </div>
          ))}
        </div>
        <div className="mt-1 flex gap-1 text-[10px] text-muted">
          {years.map(({ year }) => (
            <span key={year} className="flex-1 text-center">
              {String(year).slice(2)}
            </span>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1 text-[11px] uppercase tracking-wide text-muted">
          {t.history.perMonth}
        </p>
        <div className="flex gap-1">
          {history.days_per_month.map((days, month) => (
            <div
              key={month}
              className="flex flex-1 flex-col items-center gap-1"
            >
              <div
                className="h-5 w-full rounded-sm"
                title={`${monthName(t, month)}: ${days}`}
                style={{
                  background: TONE_HEX.bad,
                  opacity: days ? 0.25 + 0.75 * (days / monthMax) : 0.06,
                }}
              />
              <span className="text-[10px] text-muted">
                {monthName(t, month).slice(0, 1).toUpperCase()}
              </span>
            </div>
          ))}
        </div>
      </div>
      <p className="text-[11px] leading-4 text-muted">{t.history.source}</p>
    </div>
  );
}
