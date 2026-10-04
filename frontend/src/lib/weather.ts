import type { Weather } from "../api/client";
import type { Messages } from "../i18n/messages";
import { direction, formatNumber } from "../i18n/text";

export function hasWeather(weather: Weather): boolean {
  return weather.temperature_c !== null && weather.data_quality !== "NO_DATA";
}

/** Wind, gusts and rain ahead as short phrases, in that order. */
export function details(t: Messages, weather: Weather): string[] {
  const parts: string[] = [];
  if (weather.wind_speed_kmh !== null) {
    parts.push(
      t.weather.wind(
        direction(t, weather.wind_from),
        formatNumber(t, weather.wind_speed_kmh),
      ),
    );
  }
  if (weather.wind_gusts_kmh !== null) {
    parts.push(t.weather.gusts(formatNumber(t, weather.wind_gusts_kmh)));
  }
  if (weather.rain_24h_mm) {
    parts.push(t.weather.rain24h(formatNumber(t, weather.rain_24h_mm, 1)));
  }
  return parts;
}

/** "22° · wind from S 12 km/h · gusts 23 · 4 mm in 24 h" (docs/01-product.md#weather-per-field). */
export function weatherLine(t: Messages, weather: Weather): string | null {
  if (!hasWeather(weather)) return null;
  const temperature = `${formatNumber(t, weather.temperature_c ?? 0)}°`;
  return [temperature, ...details(t, weather)].join(" · ");
}
