"use client";

import type { ForecastAnswer } from "@/api/client";
import { useLocale } from "@/i18n/LocaleProvider";
import { formatNumber } from "@/i18n/text";
import { forecastTone, TONE_HEX } from "@/lib/status";

/** Three boxes (tomorrow, the day after, in 3 days), the main sentence and plain factors. */
export function ForecastSection({ forecast }: { forecast: ForecastAnswer }) {
  const { t } = useLocale();
  const tomorrow = forecast.days[0];
  if (!tomorrow) return <p className="text-sm text-slate-400">{t.forecast.noData}</p>;
  const percent = `${formatNumber(t, tomorrow.probability * 100)} %`;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        {forecast.days.map((day, i) => {
          const tone = forecastTone(day.band, forecast.data_quality);
          return (
            <div
              key={day.horizon_days}
              className="rounded-xl border p-2.5 text-center"
              style={{ borderColor: `${TONE_HEX[tone]}66`, background: `${TONE_HEX[tone]}1f` }}
            >
              <p className="text-[11px] uppercase tracking-wide text-muted">{t.forecast.days[i]}</p>
              <p className="mt-0.5 font-semibold" style={{ color: TONE_HEX[tone] }}>
                {t.forecast.band[day.band] ?? day.band}
              </p>
              <p className="text-xs text-slate-400">{formatNumber(t, day.probability * 100)} %</p>
            </div>
          );
        })}
      </div>
      <p className="text-sm text-slate-200">{t.forecast.sentence(percent)}</p>
      <div>
        <p className="mb-1 text-[11px] uppercase tracking-wide text-muted">{t.forecast.why}</p>
        {tomorrow.factors.length === 0 ? (
          <p className="text-sm text-slate-300">{t.forecast.nothingUnusual}</p>
        ) : (
          <ul className="space-y-0.5 text-sm text-slate-300">
            {tomorrow.factors.map((factor) => (
              <li key={factor.code}>{t.forecast.factors[factor.code]?.(factor.value) ?? factor.code}</li>
            ))}
          </ul>
        )}
      </div>
      {forecast.data_quality === "PARTIAL" && <p className="text-xs text-slate-400">{t.forecast.stale}</p>}
      <p className="text-[11px] leading-4 text-muted">{t.forecast.note}</p>
    </div>
  );
}
