"use client";

import type { SprayHour, Weather } from "@/api/client";
import { useLocale } from "@/i18n/LocaleProvider";
import { formatAge, formatNumber, localTime } from "@/i18n/text";
import { details, hasWeather } from "@/lib/weather";

const BLIND = ["NO_DATA", "STALE"];
// The 48 h strip shows one column every this many hours.
const STEP_HOURS = 3;

function value(hour: SprayHour, name: string): number | null {
  const v = hour.weather[name];
  return typeof v === "number" ? v : null;
}

/** The field card's weather: now, then the next 48 h every 3 hours. */
export function WeatherSection({
  weather,
  hours,
}: {
  weather: Weather;
  hours: SprayHour[];
}) {
  const { t } = useLocale();
  if (!hasWeather(weather)) {
    return <p className="text-sm text-slate-400">{t.weather.noData}</p>;
  }
  const old = BLIND.includes(weather.data_quality);
  const strip = hours
    .filter((_, i) => i % STEP_HOURS === 0)
    .slice(0, 48 / STEP_HOURS);
  return (
    <div>
      <p
        className={`text-2xl font-semibold tabular-nums ${old ? "text-muted" : ""}`}
      >
        {formatNumber(t, weather.temperature_c ?? 0)}°
      </p>
      <p className={`text-sm ${old ? "text-muted" : "text-slate-200"}`}>
        {details(t, weather).join(" · ")}
      </p>
      <p className="mt-0.5 text-sm text-slate-400">
        {[
          weather.relative_humidity_pct !== null &&
            t.weather.humidity(formatNumber(t, weather.relative_humidity_pct)),
          weather.cloud_cover_pct !== null &&
            t.weather.clouds(formatNumber(t, weather.cloud_cover_pct)),
          weather.rain_24h_mm
            ? weather.rain_probability_pct !== null &&
              t.weather.rainChance(
                formatNumber(t, weather.rain_probability_pct),
              )
            : t.weather.noRain,
          old &&
            weather.valid_at &&
            t.weather.from(formatAge(t, weather.valid_at)),
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      {strip.length > 0 && (
        <>
          <p className="mb-1 mt-3 text-xs font-medium text-muted">
            {t.weather.next48}
          </p>
          <div className="no-scrollbar -mx-4 flex gap-1 overflow-x-auto px-4 pb-1">
            {strip.map((hour) => {
              const rain = value(hour, "precipitation_mm");
              const gusts = value(hour, "wind_gusts_kmh");
              const wind = value(hour, "wind_speed_kmh");
              const temp = value(hour, "temperature_c");
              return (
                <div
                  key={hour.valid_at}
                  className="w-16 shrink-0 rounded-xl bg-white/[0.04] px-2 py-2 text-center text-xs"
                >
                  <p className="text-muted">
                    {localTime(t, hour.valid_at, true)}
                  </p>
                  <p className="mt-1 text-sm font-semibold tabular-nums">
                    {temp === null ? "–" : `${formatNumber(t, temp)}°`}
                  </p>
                  <p className="tabular-nums text-slate-300">
                    {wind === null ? "–" : formatNumber(t, wind)}
                    {gusts !== null && `/${formatNumber(t, gusts)}`}
                  </p>
                  <p className="tabular-nums text-sky-300">
                    {rain ? `${formatNumber(t, rain, 1)} mm` : "\u00a0"}
                  </p>
                </div>
              );
            })}
          </div>
          <p className="mt-1 text-[11px] text-muted">{t.weather.stripLegend}</p>
        </>
      )}
    </div>
  );
}
